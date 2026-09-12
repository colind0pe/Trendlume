import json

import pytest

from src.core.security import secret_cipher
from src.services.provider_manager import ProviderManager


@pytest.mark.asyncio
async def test_provider_snapshot_freezes_options_but_rotates_credentials(test_session):
    manager = ProviderManager(test_session)
    snapshot = await manager.capture_snapshot()
    initial = snapshot['llm']
    model = await manager.repo.get_by_id(initial['id'])
    original_config = initial['config'].copy()
    model.config = {**model.config, 'model': 'changed-global-model'}
    model.credentials_encrypted = secret_cipher.encrypt_dict({'api_key': 'rotated-secret'})
    model.is_default = False
    await test_session.commit()
    restored = ProviderManager(test_session, snapshot=snapshot)
    resolved = await restored.resolve_config('llm')
    assert resolved.config == original_config
    assert secret_cipher.decrypt_dict(resolved.credentials_encrypted)['api_key'] == 'rotated-secret'
    assert 'rotated-secret' not in json.dumps(restored.snapshot_fingerprint_payload())
    assert 'credentials_encrypted' not in json.dumps(snapshot)
    llm = await restored.get_llm()
    assert llm.api_key == 'rotated-secret'
    assert llm.model == original_config.get('model', 'gpt-4o-mini')


@pytest.mark.asyncio
async def test_snapshot_tts_voice_and_default_selection_are_fixed(test_session):
    manager = ProviderManager(test_session)
    snapshot = await manager.capture_snapshot()
    voice = await manager.get_default_tts_voice()
    selected = await manager.repo.get_by_id(snapshot['tts']['id'])
    selected.config = {**selected.config, 'default_voice': 'different-voice'}
    await test_session.commit()
    assert await ProviderManager(test_session, snapshot).get_default_tts_voice() == voice
    assert (await ProviderManager(test_session).get_default_tts_voice()) == 'different-voice'


@pytest.mark.asyncio
async def test_provider_snapshot_strips_nested_and_url_credentials(test_session):
    manager = ProviderManager(test_session)
    model = await manager.repo.get_default('llm')
    model.config = {'base_url': 'https://user:password@example.com/v1?token=hidden&region=cn',
                    'model': 'fixed', 'max_tokens': 10, 'nested': {'private_key': 'hidden', 'api_key': 'hidden',
                                                                    'access_token': 'volcengine-access-token'}}
    await test_session.commit()
    snapshot = await manager.capture_snapshot()
    rendered = json.dumps(snapshot)
    assert 'hidden' not in rendered and 'password' not in rendered
    assert 'volcengine-access-token' not in rendered
    assert snapshot['llm']['config']['max_tokens'] == 10
    restored = await ProviderManager(test_session, snapshot).resolve_config('llm')
    from urllib.parse import parse_qsl, urlsplit
    actual, expected = urlsplit(restored.config['base_url']), urlsplit(model.config['base_url'])
    assert actual.netloc == expected.netloc
    assert dict(parse_qsl(actual.query)) == dict(parse_qsl(expected.query))


@pytest.mark.asyncio
async def test_snapshot_does_not_follow_new_default(test_session):
    from src.models.provider_config import ProviderConfigModel
    manager = ProviderManager(test_session)
    snapshot = await manager.capture_snapshot()
    original = snapshot['llm']['id']
    new = ProviderConfigModel(id='new-default', provider_type='llm', provider_name='custom', display_name='New default', enabled=True, is_default=False, config={'model': 'new'})
    test_session.add(new)
    await test_session.flush()
    await manager.repo.set_default(new.id, 'llm')
    await test_session.commit()
    assert (await ProviderManager(test_session).resolve_config('llm')).id == new.id
    assert (await ProviderManager(test_session, snapshot).resolve_config('llm')).id == original
