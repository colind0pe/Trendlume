"""Store Drama dialogue only as normalized dialogue-line records."""

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "010_normalize_drama_dialogue"
down_revision: str | None = "009_remove_template_aliases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _split_dialogue(value: str) -> list[tuple[str, str]]:
    result = []
    for raw_line in re.split(r"\n+", value or ""):
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([^:：]{1,40})\s*[:：]\s*(.+)$", line)
        if match:
            result.append((match.group(1).strip(), match.group(2).strip()))
        else:
            result.append(("旁白", line))
    return result


def upgrade() -> None:
    bind = op.get_bind()
    shots = sa.table(
        "drama_shots",
        sa.column("id", sa.String(length=36)),
        sa.column("dialogue", sa.Text()),
    )
    lines = sa.table(
        "drama_dialogue_lines",
        sa.column("id", sa.String(length=36)),
        sa.column("shot_id", sa.String(length=36)),
        sa.column("sequence_index", sa.Integer()),
        sa.column("character_id", sa.String(length=36)),
        sa.column("speaker_name", sa.String(length=120)),
        sa.column("text", sa.Text()),
        sa.column("delivery", sa.String(length=160)),
        sa.column("timing_hint", sa.String(length=120)),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    existing_shot_ids = {
        shot_id for (shot_id,) in bind.execute(sa.select(lines.c.shot_id)).all()
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    for shot_id, dialogue in bind.execute(sa.select(shots.c.id, shots.c.dialogue)).all():
        if shot_id in existing_shot_ids or not str(dialogue or "").strip():
            continue
        for index, (speaker_name, text) in enumerate(_split_dialogue(str(dialogue)), start=1):
            bind.execute(
                lines.insert().values(
                    id=f"dialogue_{uuid4().hex[:12]}",
                    shot_id=shot_id,
                    sequence_index=index,
                    character_id=None,
                    speaker_name=speaker_name,
                    text=text,
                    delivery="自然",
                    timing_hint="",
                    created_at=now,
                    updated_at=now,
                )
            )

    with op.batch_alter_table("drama_shots") as batch_op:
        batch_op.drop_column("dialogue")


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("drama_shots") as batch_op:
        batch_op.add_column(sa.Column("dialogue", sa.Text(), nullable=False, server_default=""))

    shots = sa.table(
        "drama_shots",
        sa.column("id", sa.String(length=36)),
        sa.column("dialogue", sa.Text()),
    )
    lines = sa.table(
        "drama_dialogue_lines",
        sa.column("shot_id", sa.String(length=36)),
        sa.column("sequence_index", sa.Integer()),
        sa.column("speaker_name", sa.String(length=120)),
        sa.column("text", sa.Text()),
    )
    for shot_id, in bind.execute(sa.select(shots.c.id)).all():
        dialogue = "\n".join(
            f"{speaker}: {text}" if speaker != "旁白" else text
            for speaker, text in bind.execute(
                sa.select(lines.c.speaker_name, lines.c.text)
                .where(lines.c.shot_id == shot_id)
                .order_by(lines.c.sequence_index)
            ).all()
        )
        bind.execute(
            shots.update().where(shots.c.id == shot_id).values(dialogue=dialogue)
        )
