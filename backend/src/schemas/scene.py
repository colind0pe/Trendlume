from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class SceneAnimationState(BaseModel):
    """One visual state and the amount of time it stays on the timeline.

    Legacy pose-shaped keys remain the serialized storage contract so existing
    scenes and clients continue to work. Internal names deliberately describe
    people, products, objects, scenes, text, and infographics equally well.
    """

    state_id: str | None = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("state_id", "pose_id"),
        serialization_alias="pose_id",
    )
    asset_id: str = Field(min_length=1, max_length=64)
    hold: float = Field(default=0.5, gt=0.0, le=60.0)
    state: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("state", "description", "pose_description"),
        serialization_alias="description",
    )
    camera: str | None = Field(
        default=None,
        max_length=200,
        validation_alias=AliasChoices("camera", "framing", "framing_hint"),
        serialization_alias="framing",
    )
    elements: str | None = Field(
        default=None,
        max_length=200,
        validation_alias=AliasChoices("elements", "prop", "prop_hint"),
        serialization_alias="prop",
    )
    motion: str | None = Field(
        default=None,
        max_length=200,
        validation_alias=AliasChoices("motion", "expression", "expression_hint"),
        serialization_alias="expression",
    )
    transition: Literal["stepped", "blink", "mouth", "head", "expression"] = "stepped"

    @model_validator(mode="before")
    @classmethod
    def normalize_hint_names(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "transition" not in data and "transition_mode" in data:
            data["transition"] = data["transition_mode"]
        return data

    # Compatibility accessors for the renderer and third-party callers that
    # still use the original pose vocabulary.
    @property
    def pose_id(self) -> str | None:
        return self.state_id

    @property
    def description(self) -> str | None:
        return self.state

    @property
    def framing(self) -> str | None:
        return self.camera

    @property
    def prop(self) -> str | None:
        return self.elements

    @property
    def expression(self) -> str | None:
        return self.motion


class SceneMotionPlanState(BaseModel):
    """A planned visual state before an image Asset has been generated."""

    state_id: str = Field(
        min_length=1,
        max_length=64,
        validation_alias=AliasChoices("state_id", "pose_id", "id"),
        serialization_alias="pose_id",
    )
    state_name: str = Field(
        default="关键状态",
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices("state_name", "pose_name", "name"),
        serialization_alias="pose_name",
    )
    state_description: str = Field(
        default="",
        max_length=500,
        validation_alias=AliasChoices("state_description", "pose_description", "description"),
        serialization_alias="pose_description",
    )
    motion_hint: str = Field(
        default="",
        max_length=200,
        validation_alias=AliasChoices("motion_hint", "expression_hint", "expression"),
        serialization_alias="expression_hint",
    )
    camera_hint: str = Field(
        default="",
        max_length=200,
        validation_alias=AliasChoices("camera_hint", "framing_hint", "framing"),
        serialization_alias="framing_hint",
    )
    element_hint: str = Field(
        default="",
        max_length=200,
        validation_alias=AliasChoices("element_hint", "prop_hint", "prop"),
        serialization_alias="prop_hint",
    )
    recommended_hold_duration: float = Field(default=0.5, gt=0.0, le=60.0)
    transition: Literal["stepped", "blink", "mouth", "head", "expression"] = "stepped"
    asset_id: str | None = Field(default=None, max_length=64)
    status: Literal["pending", "generating", "completed", "failed"] = "pending"
    error_message: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="before")
    @classmethod
    def normalize_plan_names(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for canonical, aliases in (
            ("recommended_hold_duration", ("hold", "recommended_duration")),
            ("transition", ("transition_mode",)),
        ):
            if canonical in data:
                continue
            for alias in aliases:
                if alias in data:
                    data[canonical] = data[alias]
                    break
        return data

    @property
    def pose_id(self) -> str:
        return self.state_id

    @property
    def pose_name(self) -> str:
        return self.state_name

    @property
    def pose_description(self) -> str:
        return self.state_description

    @property
    def expression_hint(self) -> str:
        return self.motion_hint

    @property
    def framing_hint(self) -> str:
        return self.camera_hint

    @property
    def prop_hint(self) -> str:
        return self.element_hint


# Public compatibility names. New code should use the state-based names above.
SceneAnimationPose = SceneAnimationState
SceneMotionPlanPose = SceneMotionPlanState


class SceneMotionPlan(BaseModel):
    """Persisted planning contract used to generate ordered visual states."""

    version: int = Field(default=1, ge=1, le=10)
    mode: Literal["enhanced_stop_motion"] = "enhanced_stop_motion"
    source: Literal["llm", "template"] = "template"
    status: Literal["planned", "generating", "partial", "completed", "failed"] = "planned"
    style_preset: str = Field(default="cinematic_real", min_length=1, max_length=64)
    reference_asset_id: str | None = Field(default=None, max_length=64)
    pose_fps: float = Field(default=10.0, ge=8.0, le=12.0)
    output_fps: Literal[24, 30] = 30
    states: list[SceneMotionPlanState] = Field(
        min_length=3,
        max_length=6,
        validation_alias=AliasChoices("states", "poses"),
        serialization_alias="poses",
    )
    error_message: str | None = Field(default=None, max_length=1000)

    @property
    def poses(self) -> list[SceneMotionPlanState]:
        return self.states


class SceneMicroMotionSpec(BaseModel):
    """Small, bounded transforms applied while a visual state is on screen."""

    enabled: bool = False
    pulse: bool = Field(
        default=False,
        validation_alias=AliasChoices("pulse", "blink"),
        serialization_alias="blink",
    )
    pulse_interval_seconds: float = Field(
        default=2.8,
        ge=0.5,
        le=10.0,
        validation_alias=AliasChoices("pulse_interval_seconds", "blink_interval_seconds"),
        serialization_alias="blink_interval_seconds",
    )
    drift_y: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        validation_alias=AliasChoices("drift_y", "head_bob"),
        serialization_alias="head_bob",
    )
    breathing: float = Field(default=0.0, ge=0.0, le=0.01)
    jitter: float = Field(default=0.0, ge=0.0, le=2.0)
    scale: float = Field(default=0.0, ge=0.0, le=0.03)
    rotate: float = Field(default=0.0, ge=0.0, le=1.0)
    push: float = Field(default=0.0, ge=0.0, le=0.08)
    pan_x: float = Field(default=0.0, ge=-0.05, le=0.05)
    pan_y: float = Field(default=0.0, ge=-0.05, le=0.05)

    @model_validator(mode="before")
    @classmethod
    def normalize_pan_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        pan = data.get("pan")
        if isinstance(pan, dict):
            data.setdefault("pan_x", pan.get("x", 0.0))
            data.setdefault("pan_y", pan.get("y", 0.0))
        return data

    @property
    def blink(self) -> bool:
        return self.pulse

    @property
    def blink_interval_seconds(self) -> float:
        return self.pulse_interval_seconds

    @property
    def head_bob(self) -> float:
        return self.drift_y


class SceneParallaxLayers(BaseModel):
    """Optional existing transparent assets around the primary state layer."""

    foreground_asset_id: str | None = Field(default=None, max_length=64)
    background_asset_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="before")
    @classmethod
    def normalize_layer_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for name in ("foreground", "background"):
            canonical = f"{name}_asset_id"
            raw = data.get(name)
            if canonical not in data and isinstance(raw, str):
                data[canonical] = raw
            elif canonical not in data and isinstance(raw, dict):
                data[canonical] = raw.get("asset_id")
        return data


class SceneParallaxSpec(BaseModel):
    """Low-complexity 2.5D motion using user-provided image layers."""

    enabled: bool = False
    strength: float = Field(default=0.25, ge=0.0, le=1.0)
    layers: SceneParallaxLayers = Field(default_factory=SceneParallaxLayers)


class SceneNormalizedRect(BaseModel):
    """A normalized rectangle used for deterministic reference alignment."""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def stay_inside_source_image(self) -> "SceneNormalizedRect":
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("归一化区域必须完全位于参考图范围内")
        return self


class SceneOpticalFlowSpec(BaseModel):
    """Opt-in, local-only interpolation between explicitly small state changes."""

    enabled: bool = False
    transition_seconds: float = Field(default=0.18, ge=0.08, le=0.4)
    max_transitions: int = Field(default=2, ge=1, le=4)
    region: SceneNormalizedRect | None = None

    @model_validator(mode="after")
    def require_bounded_region(self) -> "SceneOpticalFlowSpec":
        if not self.enabled:
            return self
        if self.region is None:
            raise ValueError("启用局部光流时必须提供 optical_flow.region")
        if (
            self.region.width > 0.6
            or self.region.height > 0.6
            or self.region.width * self.region.height > 0.25
        ):
            raise ValueError("局部光流区域不能覆盖大范围画面，请缩小到局部变化区域")
        return self


class SceneSubjectAlignmentSpec(BaseModel):
    """Optional manual subject anchor for reference-image preprocessing.

    ``source_box`` is deliberately explicit: the backend does not bundle a
    subject detector, so it must not claim automatic landmark detection.
    """

    enabled: bool = False
    source_box: SceneNormalizedRect | None = None
    target_center_x: float = Field(default=0.5, ge=0.0, le=1.0)
    target_center_y: float = Field(default=0.18, ge=0.0, le=1.0)
    target_width: float = Field(default=0.12, gt=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def normalize_compatible_names(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "source_box" not in data:
            for alias in ("face_box", "bbox"):
                if alias in data:
                    data["source_box"] = data[alias]
                    break
        target_center = data.get("target_center")
        if isinstance(target_center, dict):
            data.setdefault("target_center_x", target_center.get("x", 0.5))
            data.setdefault("target_center_y", target_center.get("y", 0.18))
        if "target_width" not in data and "target_face_width" in data:
            data["target_width"] = data["target_face_width"]
        return data

    @model_validator(mode="after")
    def require_source_box_when_enabled(self) -> "SceneSubjectAlignmentSpec":
        if self.enabled and self.source_box is None:
            raise ValueError("启用主体对齐时必须提供 subject_alignment.source_box")
        return self


SceneFaceAlignmentSpec = SceneSubjectAlignmentSpec


class SceneReferenceFrameSpec(BaseModel):
    """Fixed reference canvas and optional deterministic subject alignment."""

    enabled: bool = False
    width: int = Field(default=720, ge=256, le=4096)
    height: int = Field(default=1280, ge=256, le=4096)
    fit: Literal["contain", "cover"] = "contain"
    padding_color: Literal["black", "white"] = "black"
    subject_alignment: SceneSubjectAlignmentSpec = Field(
        default_factory=SceneSubjectAlignmentSpec,
        validation_alias=AliasChoices("subject_alignment", "face_alignment"),
        serialization_alias="face_alignment",
    )

    @property
    def face_alignment(self) -> SceneSubjectAlignmentSpec:
        return self.subject_alignment


class SceneAnimationSpec(BaseModel):
    """Persisted animation settings for a Scene.

    The spec intentionally lives inside ``SceneModel.layout_params`` so older
    rows and the existing Scene API remain compatible without a migration.
    """

    mode: Literal["enhanced_stop_motion"]
    reference_asset_id: str | None = Field(default=None, max_length=64)
    pose_fps: float = Field(default=10.0, ge=8.0, le=12.0)
    output_fps: Literal[24, 30] = 30
    states: list[SceneAnimationState] = Field(
        min_length=3,
        max_length=6,
        validation_alias=AliasChoices("states", "poses"),
        serialization_alias="poses",
    )
    reference_frame: SceneReferenceFrameSpec | None = None
    micro_motion: SceneMicroMotionSpec = Field(default_factory=SceneMicroMotionSpec)
    parallax: SceneParallaxSpec = Field(default_factory=SceneParallaxSpec)
    optical_flow: SceneOpticalFlowSpec | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_compatible_reference_and_layers(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "reference_asset_id" not in data and "reference_image_asset_id" in data:
            data["reference_asset_id"] = data["reference_image_asset_id"]
        if "parallax" not in data and isinstance(data.get("layers"), dict):
            data["parallax"] = {"enabled": True, "layers": data["layers"]}
        return data

    @property
    def poses(self) -> list[SceneAnimationState]:
        return self.states


class SceneCreate(BaseModel):
    sequence_index: int = Field(default=0, ge=0)
    narration_text: str = ""
    visual_prompt: str = ""
    duration_seconds: float = 4.0
    layout_params: dict[str, Any] = Field(default_factory=dict)
    animation: SceneAnimationSpec | None = None
    audio_asset_id: str | None = None
    media_asset_id: str | None = None


class SceneUpdate(BaseModel):
    sequence_index: int | None = None
    narration_text: str | None = None
    visual_prompt: str | None = None
    duration_seconds: float | None = None
    layout_params: dict[str, Any] | None = None
    animation: SceneAnimationSpec | None = None
    audio_asset_id: str | None = None
    media_asset_id: str | None = None


class SceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    sequence_index: int
    narration_text: str
    visual_prompt: str
    duration_seconds: float
    layout_params: dict[str, Any]
    audio_asset_id: str | None = None
    media_asset_id: str | None = None
    rendered_segment_asset_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SceneBatchUpdate(BaseModel):
    scenes: list[SceneCreate]
