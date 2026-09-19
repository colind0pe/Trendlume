"""Add the independent Drama pre-production domain."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006_drama_preproduction"
down_revision: str | None = "005_creative_planning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "drama_bibles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("logline", sa.Text(), nullable=False),
        sa.Column("genre", sa.String(length=100), nullable=False),
        sa.Column("tone", sa.String(length=100), nullable=False),
        sa.Column("visual_style", sa.Text(), nullable=False),
        sa.Column("current_stage", sa.String(length=30), nullable=False),
        sa.Column("workflow_status", sa.String(length=30), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("stage_state", sa.JSON(), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("continuity_rules", sa.JSON(), nullable=False),
        sa.Column("prop_locks", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drama_bibles_project_id", "drama_bibles", ["project_id"], unique=False)
    op.create_index(
        "ix_drama_bibles_project_updated",
        "drama_bibles",
        ["project_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "drama_characters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bible_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("appearance_lock", sa.Text(), nullable=False),
        sa.Column("wardrobe", sa.Text(), nullable=False),
        sa.Column("voice_id", sa.String(length=120), nullable=True),
        sa.Column("reference_asset_id", sa.String(length=36), nullable=True),
        sa.Column("prompt_anchor", sa.String(length=160), nullable=False),
        sa.Column("continuity_metadata", sa.JSON(), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["bible_id"], ["drama_bibles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reference_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drama_characters_bible_id", "drama_characters", ["bible_id"], unique=False)
    op.create_index(
        "ix_drama_characters_bible_approval",
        "drama_characters",
        ["bible_id", "approval_status"],
        unique=False,
    )

    op.create_table(
        "drama_locations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bible_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("visual_description", sa.Text(), nullable=False),
        sa.Column("reference_asset_ids", sa.JSON(), nullable=False),
        sa.Column("prompt_anchor", sa.String(length=160), nullable=False),
        sa.Column("continuity_metadata", sa.JSON(), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["bible_id"], ["drama_bibles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drama_locations_bible_id", "drama_locations", ["bible_id"], unique=False)
    op.create_index(
        "ix_drama_locations_bible_approval",
        "drama_locations",
        ["bible_id", "approval_status"],
        unique=False,
    )

    op.create_table(
        "drama_episodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bible_id", sa.String(length=36), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("synopsis", sa.Text(), nullable=False),
        sa.Column("script_text", sa.Text(), nullable=False),
        sa.Column("continuity_metadata", sa.JSON(), nullable=False),
        sa.Column("workflow_status", sa.String(length=30), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["bible_id"], ["drama_bibles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bible_id", "episode_number", name="uq_drama_episode_number"),
    )
    op.create_index("ix_drama_episodes_bible_id", "drama_episodes", ["bible_id"], unique=False)
    op.create_index(
        "ix_drama_episodes_bible_status",
        "drama_episodes",
        ["bible_id", "approval_status"],
        unique=False,
    )

    op.create_table(
        "drama_scenes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("beat", sa.Text(), nullable=False),
        sa.Column("location_id", sa.String(length=36), nullable=True),
        sa.Column("script_text", sa.Text(), nullable=False),
        sa.Column("continuity_metadata", sa.JSON(), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["episode_id"], ["drama_episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["drama_locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", "sequence_index", name="uq_drama_scene_sequence"),
    )
    op.create_index("ix_drama_scenes_episode_id", "drama_scenes", ["episode_id"], unique=False)
    op.create_index(
        "ix_drama_scenes_episode_status",
        "drama_scenes",
        ["episode_id", "approval_status"],
        unique=False,
    )

    op.create_table(
        "drama_shots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scene_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("dialogue", sa.Text(), nullable=False),
        sa.Column("character_ids", sa.JSON(), nullable=False),
        sa.Column("location_id", sa.String(length=36), nullable=True),
        sa.Column("camera", sa.String(length=255), nullable=False),
        sa.Column("framing", sa.String(length=120), nullable=False),
        sa.Column("movement", sa.String(length=255), nullable=False),
        sa.Column("duration_hint", sa.Float(), nullable=False),
        sa.Column("visual_prompt", sa.Text(), nullable=False),
        sa.Column("prompt_anchor", sa.String(length=180), nullable=False),
        sa.Column("continuity_metadata", sa.JSON(), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["scene_id"], ["drama_scenes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["drama_locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scene_id", "sequence_index", name="uq_drama_shot_sequence"),
    )
    op.create_index("ix_drama_shots_scene_id", "drama_shots", ["scene_id"], unique=False)
    op.create_index(
        "ix_drama_shots_scene_status",
        "drama_shots",
        ["scene_id", "approval_status"],
        unique=False,
    )

    op.create_table(
        "drama_dialogue_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("shot_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.String(length=36), nullable=True),
        sa.Column("speaker_name", sa.String(length=120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("delivery", sa.String(length=160), nullable=False),
        sa.Column("timing_hint", sa.String(length=120), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["shot_id"], ["drama_shots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_id"], ["drama_characters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shot_id", "sequence_index", name="uq_drama_dialogue_sequence"),
    )
    op.create_index(
        "ix_drama_dialogue_lines_shot_id",
        "drama_dialogue_lines",
        ["shot_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_drama_dialogue_lines_shot_id", table_name="drama_dialogue_lines")
    op.drop_table("drama_dialogue_lines")
    op.drop_index("ix_drama_shots_scene_status", table_name="drama_shots")
    op.drop_index("ix_drama_shots_scene_id", table_name="drama_shots")
    op.drop_table("drama_shots")
    op.drop_index("ix_drama_scenes_episode_status", table_name="drama_scenes")
    op.drop_index("ix_drama_scenes_episode_id", table_name="drama_scenes")
    op.drop_table("drama_scenes")
    op.drop_index("ix_drama_episodes_bible_status", table_name="drama_episodes")
    op.drop_index("ix_drama_episodes_bible_id", table_name="drama_episodes")
    op.drop_table("drama_episodes")
    op.drop_index("ix_drama_locations_bible_approval", table_name="drama_locations")
    op.drop_index("ix_drama_locations_bible_id", table_name="drama_locations")
    op.drop_table("drama_locations")
    op.drop_index("ix_drama_characters_bible_approval", table_name="drama_characters")
    op.drop_index("ix_drama_characters_bible_id", table_name="drama_characters")
    op.drop_table("drama_characters")
    op.drop_index("ix_drama_bibles_project_updated", table_name="drama_bibles")
    op.drop_index("ix_drama_bibles_project_id", table_name="drama_bibles")
    op.drop_table("drama_bibles")
