"""UE 5.6 TakeRecorderSubsystem glue for generic NVIDIA ACE MetaHumans."""

import hashlib
import bisect
import json
import math
import os
import re
import time
import traceback
from pathlib import Path

import unreal


LOG_PREFIX = "[A2F-METAHUMAN-CAPTURE]"
TICK_RESOLUTION = 24000
UNREAL_NAME = r"[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*"


class A2FMetaHumanCapture:
    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve()
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.status_path = Path(self.config["status_path"]).resolve()
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.take = unreal.get_engine_subsystem(unreal.TakeRecorderSubsystem)
        self.asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        self.editor_avatar = None
        self.editor_face = None
        self.camera = None
        self.avatar_info = None
        self.run_map_path = self.config.get(
            "map_path", "/Game/Maps/TaroA2F/TaroFaceBodyDemo_Repaired"
        )
        self.shot_sequences = []
        self.game_avatar = None
        self.face_animation = None
        self.body_animation = None
        self.baked_body_animation = None
        self.baked_face_animation = None
        self.pre_transform_face_animation = None
        self.face_curve_motion = None
        self.post_transform_curve_motion = None
        self.curve_application = None
        self.ace_blendshape_override_nodes = 0
        self.capture_sequence = None
        self.final_sequence = None
        self.take_started_at = None
        self.animation_started_at = None
        self.animation_ended_at = None
        self.phase = "setup"
        self.deadline = time.monotonic() + 60.0
        self.done = False
        self.tick_handle = unreal.register_slate_post_tick_callback(self.tick)
        self.write_status("running", "setup")
        unreal.log(f"{LOG_PREFIX} config={self.config_path}")

    def write_status(self, status, stage, **extra):
        payload = {
            "schema_version": 1,
            "run_id": self.config["run_id"],
            "status": status,
            "stage": stage,
            "updated_at_epoch": time.time(),
            "official_api_symbols": [
                "UACEBlueprintLibrary::AnimateCharacterFromWavFile",
                "UAsyncActionAnimateCharacter::AnimateCharacterFromWavFileAsync",
                "UTakeRecorderSubsystem::SetTargetSequence",
                "UTakeRecorderSubsystem::AddSourceForActor",
                "UTakeRecorderSubsystem::StartRecording",
                "UTakeRecorderSubsystem::StopRecording",
                "UTakeRecorderSubsystem::TakeRecorderFinished",
            ],
        }
        payload.update(extra)
        temporary = self.status_path.with_suffix(self.status_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.status_path)

    def fail(self, stage, exc):
        if self.done:
            return
        self.done = True
        unreal.log_error(f"{LOG_PREFIX} stage={stage} error={exc}")
        self.write_status(
            "failure", stage, error=str(exc), traceback=traceback.format_exc()
        )
        if self.tick_handle is not None:
            unreal.unregister_slate_post_tick_callback(self.tick_handle)
            self.tick_handle = None

    def manual_boundary(self, stage, message, **extra):
        self.done = True
        payload = {
            "error": message,
            "requested_avatar": self.config.get("avatar_selector", "Taro"),
        }
        payload.update(extra)
        self.write_status("manual_action_required", stage, **payload)
        if self.tick_handle is not None:
            unreal.unregister_slate_post_tick_callback(self.tick_handle)
            self.tick_handle = None

    @staticmethod
    def canonical_avatar_path(value):
        package, separator, object_name = value.partition(".")
        package_name = package.rsplit("/", 1)[-1]
        if (
            not re.fullmatch(rf"/Game(?:/{UNREAL_NAME})+", package)
            or ".." in package
        ):
            raise RuntimeError("avatar path must be a safe /Game path")
        if separator and object_name != package_name:
            raise RuntimeError("avatar object name must match package name")
        return value if separator else f"{package}.{package_name}"

    @staticmethod
    def avatar_record(data):
        asset_name = str(data.asset_name)
        if (
            not asset_name.startswith("BP_")
            or "Preview" in asset_name
            or str(data.asset_class_path.asset_name) != "Blueprint"
        ):
            return None
        package_name = str(data.package_name)
        return {
            "asset_name": asset_name,
            "object_path": f"{package_name}.{asset_name}",
            "generated_class_path": f"{package_name}.{asset_name}_C",
        }

    def avatar_catalog(self):
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        registry.wait_for_completion()
        result = []
        for data in registry.get_assets_by_path(
            unreal.Name("/Game/MetaHumans"), recursive=True
        ):
            record = self.avatar_record(data)
            if record is not None:
                result.append(record)
        return result

    def resolve_avatar_asset(self):
        selector = self.config.get("avatar_selector", "Taro")
        if selector.startswith("/"):
            canonical = self.canonical_avatar_path(selector)
            registry = unreal.AssetRegistryHelpers.get_asset_registry()
            registry.wait_for_completion()
            record = self.avatar_record(
                registry.get_asset_by_object_path(canonical)
            )
            matches = [record] if record and record["object_path"] == canonical else []
            method = "asset_path"
        else:
            catalog = self.avatar_catalog()
            requested = selector[3:] if selector.lower().startswith("bp_") else selector
            matches = [
                item
                for item in catalog
                if item["asset_name"][3:].casefold() == requested.casefold()
            ]
            method = "name"
        if not matches:
            self.manual_boundary(
                "avatar_import_required",
                f"MetaHuman avatar is not present under /Game/MetaHumans: {selector}",
                official_import_path="/Game/MetaHumans",
            )
            return None
        if len(matches) > 1:
            raise RuntimeError(
                "avatar selector is ambiguous: "
                + ", ".join(sorted(item["object_path"] for item in matches))
            )
        resolved = dict(matches[0])
        resolved["requested"] = selector
        resolved["resolution_method"] = method
        resolved["class_name"] = resolved["asset_name"] + "_C"
        return resolved

    def find_avatar(self, world):
        if self.avatar_info is None:
            return None
        return next(
            (
                actor
                for actor in unreal.GameplayStatics.get_all_actors_of_class(
                    world, unreal.Actor
                )
                if actor.get_actor_label() == self.avatar_info.get("actor_label")
                or actor.get_class().get_name() == self.avatar_info["class_name"]
            ),
            None,
        )

    def apply_avatar_visual_profile(self, actor):
        profile = self.config.get("avatar_visual_profile", "source")
        if profile == "source":
            return {
                "id": "source",
                "applied": False,
                "source_asset_modified": False,
            }
        if profile != "face-focused-vulkan-safe":
            raise RuntimeError(f"unsupported avatar visual profile: {profile}")

        material_path = (
            "/Game/Audio2FaceDemo/Materials/"
            "M_TaroTop_VulkanSafe.M_TaroTop_VulkanSafe"
        )
        safe_material = unreal.EditorAssetLibrary.load_asset(material_path)
        if safe_material is None:
            raise RuntimeError("Vulkan-safe torso material is unavailable")

        torso = None
        hidden = []
        for component in actor.get_components_by_class(unreal.SkeletalMeshComponent):
            name = component.get_name()
            if name in ("Legs", "Feet"):
                component.set_visibility(False, True)
                component.set_hidden_in_game(True, True)
                hidden.append(name)
            elif name in ("Face", "Body", "Torso"):
                component.set_visibility(True, True)
                component.set_hidden_in_game(False, True)
            if name == "Torso":
                torso = component
        if torso is None:
            raise RuntimeError("MetaHuman Torso component is unavailable")
        material_slots = int(torso.get_num_materials())
        if material_slots < 1:
            raise RuntimeError("MetaHuman Torso has no material slots")
        for material_index in range(material_slots):
            torso.set_material(material_index, safe_material)
        return {
            "id": profile,
            "applied": True,
            "scope": "run-owned-actor-instance",
            "source_asset_modified": False,
            "visible_components": ["Face", "Body", "Torso", "all-grooms"],
            "hidden_components": sorted(hidden),
            "torso_material_override": material_path,
            "torso_material_slots": material_slots,
            "reason": "UE 5.6 Linux Vulkan fabric shader workaround",
        }

    def prepare_avatar_world(self):
        self.avatar_info = self.resolve_avatar_asset()
        if self.avatar_info is None:
            return None
        world = self.editor.get_editor_world()
        if world is None:
            raise RuntimeError("editor world is unavailable")
        is_default_taro = self.avatar_info["object_path"] == (
            "/Game/MetaHumans/Taro/BP_Taro.BP_Taro"
        )
        if is_default_taro:
            self.avatar_info["actor_label"] = "Taro_A2F_FaceBodyDemo"
            actor = self.find_avatar(world)
            if actor is None:
                raise RuntimeError("default Taro actor is missing from the production map")
            self.avatar_info["source_asset_modified"] = False
            return world

        run_map = f"{self.config['asset_root']}/RunMap"
        # Save the already loaded template world under the run-owned path.  Loading a
        # UWorld returned by duplicate_asset in the same Python tick leaves that same
        # World referenced and UE 5.6 aborts while trying to garbage-collect it.
        if not unreal.EditorLoadingAndSavingUtils.save_map(world, run_map):
            raise RuntimeError("could not save the run-owned map")
        self.run_map_path = run_map
        # save_map is Save-As-to-disk; it does not switch the editor's current
        # world. Drop the Python reference before loading the run-owned copy so
        # all instance edits and the later save_current_level stay isolated.
        world = None
        if not self.level_editor.load_level(run_map):
            raise RuntimeError("could not load the run-owned map")
        world = self.editor.get_editor_world()
        if world is None or run_map not in world.get_path_name():
            raise RuntimeError("run-owned map did not become the editor world")
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        original_actor = next(
            (
                actor
                for actor in unreal.GameplayStatics.get_all_actors_of_class(
                    world, unreal.Actor
                )
                if actor.get_actor_label() == "Taro_A2F_FaceBodyDemo"
                or actor.get_class().get_name() == "BP_Taro_C"
            ),
            None,
        )
        spawn_location = (
            original_actor.get_actor_location()
            if original_actor
            else unreal.Vector(-100.0, 0.0, 0.0)
        )
        spawn_rotation = (
            original_actor.get_actor_rotation()
            if original_actor
            else unreal.Rotator(0.0, 0.0, 0.0)
        )
        if original_actor:
            actor_subsystem.destroy_actor(original_actor)
        blueprint_class = unreal.EditorAssetLibrary.load_blueprint_class(
            self.avatar_info["object_path"]
        )
        if blueprint_class is None:
            raise RuntimeError("resolved avatar Blueprint class could not be loaded")
        actor = actor_subsystem.spawn_actor_from_class(
            blueprint_class, spawn_location, spawn_rotation
        )
        if actor is None:
            raise RuntimeError("resolved MetaHuman could not be spawned")
        actor_label = f"A2F_MetaHuman_{self.avatar_info['asset_name'][3:]}"
        actor.set_actor_label(actor_label)
        self.avatar_info["actor_label"] = actor_label
        if not unreal.KairosDemoEditorLibrary.configure_meta_human_actor_for_ace(actor):
            self.manual_boundary(
                "avatar_ace_setup_required",
                "MetaHuman Face/Face_AnimBP/ACE component readiness failed",
                canonical_asset_path=self.avatar_info["object_path"],
            )
            return None
        self.avatar_info["visual_profile"] = self.apply_avatar_visual_profile(actor)
        if not self.level_editor.save_current_level():
            raise RuntimeError("could not save the run-owned MetaHuman map")
        self.avatar_info["source_asset_modified"] = False
        return world

    @staticmethod
    def find_face(avatar):
        return next(
            (
                component
                for component in avatar.get_components_by_class(
                    unreal.SkeletalMeshComponent
                )
                if component.get_name() == "Face"
            ),
            None,
        )

    @staticmethod
    def find_body(avatar):
        return next(
            (
                component
                for component in avatar.get_components_by_class(
                    unreal.SkeletalMeshComponent
                )
                if component.get_name() == "Body"
            ),
            None,
        )

    @staticmethod
    def find_ace(avatar):
        return next(
            (
                component
                for component in avatar.get_components_by_class(unreal.ActorComponent)
                if "ACEAudioCurveSource" in component.get_class().get_name()
                or component.get_name() == "ACEAudioCurveSource"
            ),
            None,
        )

    def create_level_sequence(self, name):
        path = f"{self.config['asset_root']}/{name}"
        sequence = unreal.EditorAssetLibrary.load_asset(path)
        head_enabled = bool(
            ((self.config.get("head_motion") or {}).get("config") or {}).get(
                "enabled"
            )
        )
        if sequence is not None and head_enabled:
            raise RuntimeError(
                f"run-owned head-motion sequence already exists: {path}"
            )
        if sequence is None:
            sequence = self.asset_tools.create_asset(
                name,
                self.config["asset_root"],
                unreal.LevelSequence,
                unreal.LevelSequenceFactoryNew(),
            )
        if sequence is None:
            raise RuntimeError(f"could not create {path}")
        return sequence

    def setup_take_recorder(self):
        # save_map can pump Slate while saving.  Claim the setup phase first so a
        # nested post-tick cannot enter this method a second time.
        self.phase = "prepare_avatar_world"
        world = self.prepare_avatar_world()
        if world is None:
            return False
        self.editor_avatar = self.find_avatar(world)
        self.editor_face = self.find_face(self.editor_avatar) if self.editor_avatar else None
        self.camera = next(
            (
                actor
                for actor in unreal.GameplayStatics.get_all_actors_of_class(
                    world, unreal.CineCameraActor
                )
                if actor.get_actor_label() == "Taro_A2F_FinalCamera"
            ),
            None,
        )
        if self.editor_avatar is None or self.editor_face is None or self.camera is None:
            raise RuntimeError("MetaHuman, Face, or final camera is missing")
        focus = self.camera.get_cine_camera_component().get_editor_property(
            "focus_settings"
        )
        focus_distance = float(focus.get_editor_property("manual_focus_distance"))
        if abs(focus_distance - 96.4) > 0.2:
            raise RuntimeError(
                f"camera focus must be 96.4 cm, found {focus_distance:.3f}"
            )

        self.capture_sequence = self.create_level_sequence("CaptureSequence")
        fps = int(self.config["fps"])
        capture_frames = int(self.config["expected_frames"]) + fps * 120
        unreal.MovieSceneSequenceExtensions.set_display_rate(
            self.capture_sequence, unreal.FrameRate(fps, 1)
        )
        unreal.MovieSceneSequenceExtensions.set_playback_start(
            self.capture_sequence, 0
        )
        unreal.MovieSceneSequenceExtensions.set_playback_end(
            self.capture_sequence, capture_frames
        )
        target = unreal.TakeRecorderSequenceParameters()
        target.set_editor_property("record_into_sequence", self.capture_sequence)
        self.take.set_target_sequence(target)
        self.take.clear_sources()
        self.take.add_source_for_actor(self.editor_avatar, False, False)
        self.take.set_slate_name(self.config["slate"], False)
        self.take.set_frame_rate(unreal.FrameRate(fps, 1))
        self.take.set_sequence_countdown(0.0)
        settings = self.take.get_global_record_settings()
        settings.user.countdown_seconds = 0.0
        settings.user.maximize_viewport = False
        settings.user.save_recorded_assets = True
        settings.user.auto_lock = False
        settings.user.remove_redundant_tracks = False
        settings.project.record_sources_into_sub_sequences = False
        settings.project.record_to_possessable = True
        settings.project.start_at_current_timecode = False
        settings.project.show_notifications = False
        settings.open_sequencer = False
        self.take.set_global_record_settings(settings)
        self.take.take_recorder_started.add_callable_unique(self.on_take_started)
        self.take.take_recorder_finished.add_callable_unique(self.on_take_finished)

        self.level_editor.editor_request_begin_play()
        self.phase = "wait_pie"
        self.deadline = time.monotonic() + 60.0
        self.write_status(
            "running",
            "pie_start",
            avatar=self.avatar_info,
            map_path=self.run_map_path,
        )
        unreal.log(
            f"{LOG_PREFIX} TakeRecorderSubsystem configured"
            f" target={self.capture_sequence.get_path_name()}"
        )
        return True

    def start_recording(self):
        game_world = self.editor.get_game_world()
        if game_world is None:
            return False
        self.game_avatar = self.find_avatar(game_world)
        ace = self.find_ace(self.game_avatar) if self.game_avatar else None
        if self.game_avatar is None or ace is None:
            return False
        ace.on_animation_started.add_callable_unique(self.on_animation_started)
        ace.on_animation_ended.add_callable_unique(self.on_animation_ended)
        # UE 5.6 RecordIntoSequence requires a valid Sequencer instance in
        # UTakeRecorder::SetupDestinationAsset, even for an offscreen run.
        self.phase = "wait_take_initialized"
        self.deadline = time.monotonic() + 30.0
        if not self.take.start_recording(True, False):
            raise RuntimeError("TakeRecorderSubsystem.start_recording returned false")
        self.write_status("running", self.phase)
        return True

    def on_take_started(self):
        self.phase = "wait_recorder_state_started"
        self.deadline = time.monotonic() + 30.0
        self.write_status("running", "take_initialized")
        unreal.log(f"{LOG_PREFIX} Take Recorder initialized; waiting for Started state")

    def request_a2f(self):
        self.take_started_at = time.monotonic()
        endpoint = self.config["nim_endpoint"]
        if not endpoint.startswith(("http://", "https://")):
            endpoint = "http://" + endpoint
        connection = unreal.ACEConnectionInfo()
        connection.set_editor_property("dest_url", endpoint)
        unreal.ACEBlueprintLibrary.set_a2x_connection_info(
            connection, unreal.Name("RemoteA2F")
        )

        runtime = self.config.get("ace_runtime_parameters", {})
        runtime_curves = runtime.get("curve_parameters", {})
        multipliers = {
            unreal.Name(name): float(value)
            for name, value in runtime_curves.get("multipliers", {}).items()
        }
        offsets = {
            unreal.Name(name): float(value)
            for name, value in runtime_curves.get("offsets", {}).items()
        }
        if multipliers or offsets:
            self.ace_blendshape_override_nodes = int(
                unreal.KairosDemoEditorLibrary.configure_ace_blendshape_overrides(
                    self.game_avatar, multipliers, offsets
                )
            )
            if self.ace_blendshape_override_nodes < 1:
                self.fail(
                    "ace_curve_overrides",
                    "Apply ACE Face Animations node could not be configured",
                )
                return
        face_parameters = None
        face_values = runtime.get("face_parameters", {})
        if face_values:
            face_parameters = unreal.ACEBlueprintLibrary.create_audio2_face_parameters(
                self.game_avatar
            )
            face_parameters.batch_set_parameters(face_values, True)

        emotion_values = runtime.get("emotion", {})
        emotion = unreal.Audio2FaceEmotion()
        if emotion_values.get("overall_strength") is not None:
            emotion.set_editor_property(
                "overall_emotion_strength",
                float(emotion_values["overall_strength"]),
            )
        constant_emotions = emotion_values.get("constant", {})
        if constant_emotions:
            overrides = unreal.Audio2FaceEmotionOverride()
            for name, value in constant_emotions.items():
                property_name = (
                    "out_of_breath" if name == "outofbreath" else name
                )
                overrides.set_editor_property(f"override_{property_name}", True)
                overrides.set_editor_property(property_name, float(value))
            emotion.set_editor_property("enable_emotion_override", True)
            emotion.set_editor_property("emotion_override_strength", 1.0)
            emotion.set_editor_property("emotion_overrides", overrides)
        accepted = unreal.ACEBlueprintLibrary.animate_character_from_wav_file(
            self.game_avatar,
            self.config["audio_path"],
            emotion,
            face_parameters,
            unreal.Name("RemoteA2F"),
        )
        if not accepted:
            self.fail("a2f_request", "ACE rejected the WAV")
            return
        self.phase = "wait_animation_started"
        self.deadline = time.monotonic() + 90.0
        self.write_status(
            "running",
            "a2f_request",
            ace_blendshape_override_nodes=self.ace_blendshape_override_nodes,
            ace_curve_multipliers=sorted(str(name) for name in multipliers),
            ace_curve_offsets=sorted(str(name) for name in offsets),
        )
        unreal.log(
            f"{LOG_PREFIX} official ACE WAV call accepted"
            f" audio={self.config['audio_path']}"
            f" face_parameters={sorted(face_values)}"
            f" curve_override_nodes={self.ace_blendshape_override_nodes}"
            f" constant_emotions={sorted(constant_emotions)}"
        )

    def on_animation_started(self):
        self.animation_started_at = time.monotonic()
        self.phase = "animation_playing"
        self.deadline = (
            self.animation_started_at
            + float(self.config["audio_duration_seconds"])
            + 30.0
        )
        self.write_status(
            "running",
            "animation_playing",
            capture_offset_seconds=self.animation_started_at - self.take_started_at,
        )
        unreal.log(f"{LOG_PREFIX} ACE animation started")

    def on_animation_ended(self):
        self.animation_ended_at = time.monotonic()
        self.phase = "wait_take_finished"
        self.deadline = time.monotonic() + 180.0
        self.take.stop_recording()
        self.write_status("running", "take_stop")
        unreal.log(f"{LOG_PREFIX} ACE animation ended; Take Recorder stop requested")

    def on_take_finished(self, sequence_asset):
        self.capture_sequence = sequence_asset
        self.level_editor.editor_request_end_play()
        self.phase = "wait_pie_end"
        self.deadline = time.monotonic() + 60.0
        self.write_status(
            "running",
            "take_finished",
            capture_sequence=sequence_asset.get_path_name(),
        )
        unreal.log(f"{LOG_PREFIX} Take Recorder finished {sequence_asset.get_path_name()}")

    @staticmethod
    def is_face_animation(animation):
        if animation is None:
            return False
        try:
            skeleton = animation.get_editor_property("skeleton")
            return skeleton and "Face_Archetype_Skeleton" in skeleton.get_path_name()
        except Exception:
            return False

    def find_face_animation(self):
        for binding in unreal.MovieSceneSequenceExtensions.get_bindings(
            self.capture_sequence
        ):
            for track in binding.get_tracks():
                if track.get_class().get_name() != "MovieSceneSkeletalAnimationTrack":
                    continue
                for section in track.get_sections():
                    try:
                        animation = section.get_editor_property(
                            "params"
                        ).get_editor_property("animation")
                    except Exception:
                        continue
                    if self.is_face_animation(animation):
                        return animation
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        registry.scan_paths_synchronous(["/Game/Cinematics"], True)
        matches = []
        for data in registry.get_assets_by_path(
            unreal.Name("/Game/Cinematics"), recursive=True
        ):
            if self.config["slate"].lower() not in str(data.asset_name).lower():
                continue
            animation = data.get_asset()
            if self.is_face_animation(animation):
                matches.append(animation)
        if not matches:
            return None
        matches.sort(key=lambda item: float(item.get_play_length()), reverse=True)
        return matches[0]

    def find_body_animation(self, body):
        """Resolve the Take Recorder animation bound to the exact Body component."""
        body_name = body.get_name()
        body_skeleton = body.get_skeletal_mesh_asset().get_editor_property("skeleton")
        body_skeleton_path = body_skeleton.get_path_name() if body_skeleton else None
        for binding in unreal.MovieSceneSequenceExtensions.get_bindings(
            self.capture_sequence
        ):
            if str(binding.get_display_name()) != body_name:
                continue
            for track in binding.get_tracks():
                if track.get_class().get_name() != "MovieSceneSkeletalAnimationTrack":
                    continue
                for section in track.get_sections():
                    try:
                        animation = section.get_editor_property(
                            "params"
                        ).get_editor_property("animation")
                        skeleton = animation.get_editor_property("skeleton")
                    except Exception:
                        continue
                    if skeleton and skeleton.get_path_name() == body_skeleton_path:
                        return animation
        return None

    def validate_face_curve_motion(self, offset_seconds, duration_seconds):
        candidates = []
        curve_names = unreal.AnimationLibrary.get_animation_curve_names(
            self.face_animation, unreal.RawCurveTrackTypes.RCT_FLOAT
        )
        window_end = offset_seconds + duration_seconds
        for curve_name in curve_names:
            name = str(curve_name)
            normalized = name.casefold()
            if normalized != "jawopen" and not normalized.startswith("mouth"):
                continue
            times, values = unreal.AnimationLibrary.get_float_keys(
                self.face_animation, curve_name
            )
            window_values = [
                float(value)
                for time_value, value in zip(times, values)
                if offset_seconds <= float(time_value) <= window_end
            ]
            if len(window_values) < 2:
                continue
            value_range = max(window_values) - min(window_values)
            candidates.append(
                {
                    "name": name,
                    "keys_in_audio_window": len(window_values),
                    "min": min(window_values),
                    "max": max(window_values),
                    "range": value_range,
                }
            )
        candidates.sort(key=lambda item: item["range"], reverse=True)
        max_range = candidates[0]["range"] if candidates else 0.0
        if max_range < 0.05:
            raise RuntimeError(
                f"recorded face animation has insufficient mouth motion: {max_range:.6f}"
            )
        return {
            "candidate_curves": len(candidates),
            "max_range": max_range,
            "top_curves": candidates[:10],
        }

    @staticmethod
    def interpolate_curve_keys(times, values, target_time):
        right = bisect.bisect_left(times, target_time)
        if right <= 0:
            return float(values[0])
        if right >= len(times):
            return float(values[-1])
        if times[right] == target_time:
            return float(values[right])
        left = right - 1
        alpha = (target_time - times[left]) / (times[right] - times[left])
        return float(values[left]) + alpha * (
            float(values[right]) - float(values[left])
        )

    def sample_aligned_curves(self, offset_seconds):
        requested_names = self.config.get("diagnostic_curve_names", [])
        requested_frames = self.config.get("diagnostic_frame_indices", [])
        if not requested_names or not requested_frames:
            return []
        available = {
            str(name).casefold(): name
            for name in unreal.AnimationLibrary.get_animation_curve_names(
                self.face_animation, unreal.RawCurveTrackTypes.RCT_FLOAT
            )
        }
        key_data = {}
        for name in requested_names:
            curve_name = available.get(str(name).casefold())
            if curve_name is None:
                raise RuntimeError(f"diagnostic curve missing from animation: {name}")
            times, values = unreal.AnimationLibrary.get_float_keys(
                self.face_animation, curve_name
            )
            times = [float(value) for value in times]
            values = [float(value) for value in values]
            if not times or len(times) != len(values):
                raise RuntimeError(f"diagnostic curve has invalid keys: {name}")
            key_data[name] = (times, values)
        fps = int(self.config["fps"])
        result = []
        for frame_index in requested_frames:
            frame_index = int(frame_index)
            audio_time = frame_index / float(fps)
            animation_time = offset_seconds + audio_time
            result.append(
                {
                    "output_frame": frame_index,
                    "audio_time_seconds": audio_time,
                    "animation_time_seconds": animation_time,
                    "curves": {
                        name: self.interpolate_curve_keys(
                            key_data[name][0], key_data[name][1], animation_time
                        )
                        for name in requested_names
                    },
                }
            )
        return result

    def bake_effective_animation(self, offset_seconds):
        curve_application = self.config.get("curve_application", "artifact_only")
        if curve_application != "final_render":
            return {
                "mode": curve_application,
                "applied": False,
                "reason": "effective curves retained as artifact/visualization only",
                "pre_transform_asset": self.pre_transform_face_animation.get_path_name(),
            }
        motion_path = Path(self.config["effective_motion_json"]).resolve()
        if not motion_path.is_file() or motion_path.stat().st_size > 64 * 1024 * 1024:
            raise RuntimeError("effective motion JSON is missing or exceeds 64 MiB")
        digest = hashlib.sha256(motion_path.read_bytes()).hexdigest()
        lineage = self.config.get("lineage")
        if not isinstance(lineage, dict) or digest != lineage.get(
            "curve_source_sha256"
        ):
            raise RuntimeError(
                "effective motion JSON SHA does not match capture lineage"
            )
        motion = json.loads(motion_path.read_text(encoding="utf-8"))
        expected_names = list(self.config["final_render_curve_names"])
        if motion.get("curve_names", [])[: len(expected_names)] != expected_names:
            raise RuntimeError("effective motion curve order does not match ACE 2.5")
        frames = motion.get("frames")
        if not isinstance(frames, list) or len(frames) < 2:
            raise RuntimeError("effective motion requires at least two frames")
        source_asset = self.pre_transform_face_animation.get_path_name()
        source_package = source_asset.split(".", 1)[0]
        source_name = source_package.rsplit("/", 1)[-1]
        target_package = (
            f"{self.config['asset_root']}/AnimationEffective/"
            f"{source_name}_Effective"
        )
        if unreal.EditorAssetLibrary.does_asset_exist(target_package):
            raise RuntimeError("run-owned effective animation already exists")
        effective_animation = unreal.EditorAssetLibrary.duplicate_asset(
            source_package, target_package
        )
        if effective_animation is None:
            raise RuntimeError("could not duplicate run-owned face animation")
        timeline = self.config.get("timeline_policy") or {
            "curve_key_time_origin": "recorded_capture",
            "sequence_start_offset": "capture_offset",
        }
        if timeline.get("curve_key_time_origin") != "recorded_capture":
            raise RuntimeError("final-render curves must preserve capture time origin")
        if timeline.get("sequence_start_offset") != "capture_offset":
            raise RuntimeError("final-render sequence must preserve capture offset")
        times = []
        values_by_curve = [[] for _ in expected_names]
        previous_time = -1.0
        for frame_index, frame in enumerate(frames):
            timestamp = float(frame["time_seconds"])
            values = frame["values"]
            if not math.isfinite(timestamp) or timestamp <= previous_time:
                if not (frame_index == 0 and timestamp == 0.0):
                    raise RuntimeError("effective motion timecodes are invalid")
            if len(values) < len(expected_names):
                raise RuntimeError("effective motion frame has too few curves")
            previous_time = timestamp
            times.append(offset_seconds + timestamp)
            for curve_index in range(len(expected_names)):
                value = float(values[curve_index])
                if not math.isfinite(value):
                    raise RuntimeError("effective motion contains non-finite values")
                values_by_curve[curve_index].append(value)
        curve_major_values = [
            value for curve_values in values_by_curve for value in curve_values
        ]
        if not unreal.KairosDemoEditorLibrary.apply_float_curves_bulk(
            effective_animation,
            [unreal.Name(name) for name in expected_names],
            times,
            curve_major_values,
        ):
            raise RuntimeError("bulk curve application failed")
        if not unreal.EditorAssetLibrary.save_loaded_asset(
            effective_animation, only_if_is_dirty=False
        ):
            raise RuntimeError("could not save run-owned effective animation")
        self.face_animation = effective_animation
        return {
            "mode": "final_render",
            "applied": True,
            "pre_transform_asset": self.pre_transform_face_animation.get_path_name(),
            "effective_asset": effective_animation.get_path_name(),
            "source_motion_json": str(motion_path),
            "source_frames": len(frames),
            "applied_curve_count": len(expected_names),
            "applied_curve_names": expected_names,
            "time_offset_seconds": offset_seconds,
            "curve_key_time_origin_seconds": offset_seconds,
            "sequence_start_offset_seconds": offset_seconds,
            "validation_window_offset_seconds": offset_seconds,
            "timeline_policy": timeline,
            "ue_api": [
                "EditorAssetLibrary.duplicate_asset",
                "IAnimationDataController::FScopedBracket",
                "IAnimationDataController::SetCurveKeys",
            ],
        }

    def head_anchor(self):
        sockets = []
        for name in ("FACIAL_L_Eye", "FACIAL_R_Eye"):
            if self.editor_face.does_socket_exist(name):
                sockets.append(self.editor_face.get_socket_location(name))
        if len(sockets) == 2:
            return unreal.Vector(
                (sockets[0].x + sockets[1].x) / 2.0,
                (sockets[0].y + sockets[1].y) / 2.0,
                (sockets[0].z + sockets[1].z) / 2.0,
            )
        if self.editor_face.does_socket_exist("head"):
            return self.editor_face.get_socket_location("head")
        raise RuntimeError("MetaHuman face has no eye or head socket for camera framing")

    def resolved_camera(self, shot):
        camera = shot["camera"]
        anchor = self.head_anchor()
        if camera["mode"] == "orbit":
            azimuth = math.radians(float(camera["azimuth_deg"]))
            elevation = math.radians(float(camera["elevation_deg"]))
            distance = float(camera["distance_cm"])
            horizontal = distance * math.cos(elevation)
            location = unreal.Vector(
                anchor.x + horizontal * math.sin(azimuth),
                anchor.y + horizontal * math.cos(azimuth),
                anchor.z + distance * math.sin(elevation),
            )
            rotation = unreal.MathLibrary.find_look_at_rotation(location, anchor)
        else:
            values = camera["location_cm"]
            if camera["coordinate_space"] == "avatar_head":
                location = unreal.Vector(
                    anchor.x + values[0],
                    anchor.y + values[1],
                    anchor.z + values[2],
                )
            else:
                location = unreal.Vector(*values)
            rotation_values = camera["rotation_deg"]
            rotation = unreal.Rotator(
                pitch=rotation_values[0],
                yaw=rotation_values[1],
                roll=rotation_values[2],
            )
        return location, rotation, {
            "anchor_world_cm": [anchor.x, anchor.y, anchor.z],
            "location_world_cm": [location.x, location.y, location.z],
            "rotation_world_deg": [rotation.pitch, rotation.yaw, rotation.roll],
            "focal_length_mm": float(camera["focal_length_mm"]),
            "aperture": float(camera["aperture"]),
            "focus_distance_cm": float(camera["focus_distance_cm"]),
        }

    def add_camera(self, sequence, shot, use_legacy_camera):
        if use_legacy_camera:
            binding = sequence.add_possessable(self.camera)
            return binding, {
                "location_world_cm": [
                    self.camera.get_actor_location().x,
                    self.camera.get_actor_location().y,
                    self.camera.get_actor_location().z,
                ],
                "rotation_world_deg": [
                    self.camera.get_actor_rotation().pitch,
                    self.camera.get_actor_rotation().yaw,
                    self.camera.get_actor_rotation().roll,
                ],
                "focal_length_mm": 40.0,
                "aperture": 16.0,
                "focus_distance_cm": 96.4,
            }, "possessable"
        location, rotation, resolved = self.resolved_camera(shot)
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        camera_actor = actor_subsystem.spawn_actor_from_class(
            unreal.CineCameraActor, location, rotation
        )
        if camera_actor is None:
            raise RuntimeError(f"could not create camera for shot {shot['id']}")
        component = camera_actor.get_cine_camera_component()
        component.set_editor_property(
            "current_focal_length", resolved["focal_length_mm"]
        )
        component.set_editor_property("current_aperture", resolved["aperture"])
        focus = component.get_editor_property("focus_settings")
        focus.set_editor_property("focus_method", unreal.CameraFocusMethod.MANUAL)
        focus.set_editor_property(
            "manual_focus_distance", resolved["focus_distance_cm"]
        )
        focus.set_editor_property("smooth_focus_changes", False)
        component.set_editor_property("focus_settings", focus)
        binding = sequence.add_spawnable_from_instance(camera_actor)
        actor_subsystem.destroy_actor(camera_actor)
        return binding, resolved, "spawnable"

    def apply_head_motion(self, sequence, actor_binding, frame_count, offset_ticks):
        """Bake local head motion into run-owned Body/Face animations."""
        request = self.config.get("head_motion") or {}
        config = request.get("config") or {}
        if not config.get("enabled"):
            return {
                "enabled": False,
                "track_count": 0,
                "face_track_count": 1,
                "fixed_camera": True,
                "source_asset_modified": False,
            }
        lineage = self.config.get("head_motion_lineage")
        if not isinstance(lineage, dict):
            raise RuntimeError("enabled head motion has no lineage")
        artifacts = request.get("artifacts") or {}
        source_record = artifacts.get("samples_json") or {}
        source_path = Path(str(source_record.get("path", ""))).resolve()
        if not source_path.is_file() or source_path.stat().st_size > 64 * 1024 * 1024:
            raise RuntimeError("head-motion source samples are missing or oversized")
        source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if (
            source_digest != source_record.get("sha256")
            or source_digest != lineage.get("samples_sha256")
        ):
            raise RuntimeError("head-motion source sample SHA does not match lineage")
        applied_record = artifacts.get("applied_samples_json") or {}
        path = Path(str(applied_record.get("path", ""))).resolve()
        if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            raise RuntimeError("head-motion applied samples are missing or oversized")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != applied_record.get("sha256"):
            raise RuntimeError("head-motion applied sample SHA does not match record")
        document = json.loads(path.read_text(encoding="utf-8"))
        calibration = request.get("render_sync_calibration") or {}
        compensation = document.get("render_sync_compensation") or {}
        if (
            document.get("source_samples_sha256") != source_digest
            or compensation.get("video_advance_frames")
            != calibration.get("video_advance_frames")
        ):
            raise RuntimeError("head-motion render-sync compensation provenance mismatch")
        frames = document.get("frames")
        if not isinstance(frames, list) or len(frames) != frame_count:
            raise RuntimeError("head-motion frame count does not match sequence")
        canonical_config = json.dumps(
            document.get("config"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if hashlib.sha256(canonical_config).hexdigest() != lineage.get(
            "config_sha256"
        ):
            raise RuntimeError("head-motion config SHA does not match lineage")
        if (
            document.get("profile_version") != "subtle-conversational-v1"
            or document.get("coordinate_space") != "local-bone-additive"
            or int(document.get("frame_count", -1)) != frame_count
            or int(lineage.get("frame_count", -1)) != frame_count
            or int(lineage.get("fps", -1)) != int(self.config["fps"])
            or abs(float(document.get("fps", -1)) - float(self.config["fps"])) > 1e-9
        ):
            raise RuntimeError("head-motion semantic metadata is incompatible")
        limits = {
            "pitch_deg": float(config["pitch_limit_deg"]),
            "yaw_deg": float(config["yaw_limit_deg"]),
            "roll_deg": float(config["roll_limit_deg"]),
        }
        for index, frame in enumerate(frames):
            if (
                int(frame.get("frame_index", -1)) != index
                or abs(float(frame.get("time_seconds", -1)) - index / float(self.config["fps"])) > 1e-9
            ):
                raise RuntimeError("head-motion frame/time sequence is invalid")
            for axis, limit in limits.items():
                value = float(frame.get(axis, math.nan))
                if not math.isfinite(value) or abs(value) > limit + 1e-9:
                    raise RuntimeError(f"head-motion {axis} is non-finite or out of bounds")
        body = self.find_body(self.editor_avatar)
        if body is None:
            raise RuntimeError("MetaHuman Body component is unavailable for head motion")
        bones = ["neck_01", "neck_02", "head"]
        for name in bones:
            if int(body.get_bone_index(name)) < 0:
                raise RuntimeError(f"MetaHuman Body hierarchy is missing {name}")
        if str(body.get_parent_bone("head")) != "neck_02" or str(
            body.get_parent_bone("neck_02")
        ) != "neck_01":
            raise RuntimeError("MetaHuman Body head/neck parent chain is incompatible")

        fps = int(self.config["fps"])
        start_frame = round(int(offset_ticks) * fps / TICK_RESOLUTION)
        weights = [0.2, 0.3, 0.5]
        rotations = [
            unreal.Rotator(
                pitch=float(frame["pitch_deg"]),
                yaw=float(frame["yaw_deg"]),
                roll=float(frame["roll_deg"]),
            )
            for frame in frames
        ]
        if self.baked_body_animation is None:
            self.body_animation = self.find_body_animation(body)
            if self.body_animation is None:
                raise RuntimeError("recorded Body AnimSequence was not found")
            source_package = self.body_animation.get_path_name().split(".", 1)[0]
            source_name = source_package.rsplit("/", 1)[-1]
            target_package = (
                f"{self.config['asset_root']}/AnimationHead/"
                f"{source_name}_HeadMotion"
            )
            if unreal.EditorAssetLibrary.does_asset_exist(target_package):
                raise RuntimeError("run-owned baked Body animation already exists")
            self.baked_body_animation = unreal.EditorAssetLibrary.duplicate_asset(
                source_package, target_package
            )
            if self.baked_body_animation is None:
                raise RuntimeError("could not duplicate run-owned Body animation")
            if not unreal.KairosDemoEditorLibrary.apply_head_rotations_to_body_animation(
                self.baked_body_animation,
                start_frame,
                fps,
                [unreal.Name(bone) for bone in bones],
                weights,
                rotations,
            ):
                raise RuntimeError("run-owned Body head-motion bake failed")
            if not unreal.EditorAssetLibrary.save_loaded_asset(
                self.baked_body_animation, only_if_is_dirty=False
            ):
                raise RuntimeError("could not save run-owned baked Body animation")

        if self.baked_face_animation is None:
            face_source_package = self.face_animation.get_path_name().split(".", 1)[0]
            face_source_name = face_source_package.rsplit("/", 1)[-1]
            face_target_package = (
                f"{self.config['asset_root']}/AnimationHead/"
                f"{face_source_name}_HeadMotion"
            )
            if unreal.EditorAssetLibrary.does_asset_exist(face_target_package):
                raise RuntimeError("run-owned baked Face animation already exists")
            self.baked_face_animation = unreal.EditorAssetLibrary.duplicate_asset(
                face_source_package, face_target_package
            )
            if self.baked_face_animation is None:
                raise RuntimeError("could not duplicate run-owned Face animation")
            if not unreal.KairosDemoEditorLibrary.apply_head_rotations_to_body_animation(
                self.baked_face_animation,
                start_frame,
                fps,
                [unreal.Name("head")],
                [1.0],
                rotations,
            ):
                raise RuntimeError("run-owned Face head-motion bake failed")
            if not unreal.EditorAssetLibrary.save_loaded_asset(
                self.baked_face_animation, only_if_is_dirty=False
            ):
                raise RuntimeError("could not save run-owned baked Face animation")
        self.face_animation = self.baked_face_animation

        body_binding = sequence.add_possessable(body)
        body_binding.set_display_name("MetaHuman Body Head Motion")
        body_binding.set_parent(actor_binding)
        body_track = body_binding.add_track(unreal.MovieSceneSkeletalAnimationTrack)
        body_section = body_track.add_section()
        body_section.set_start_frame(0)
        body_section.set_end_frame(frame_count)
        body_params = unreal.MovieSceneSkeletalAnimationParams()
        body_params.set_editor_property("animation", self.baked_body_animation)
        body_params.set_editor_property(
            "start_frame_offset", unreal.FrameNumber(offset_ticks)
        )
        body_params.set_editor_property("force_custom_mode", True)
        body_section.set_editor_property("params", body_params)
        body_animation_tracks = [
            track
            for track in body_binding.get_tracks()
            if track.get_class().get_name() == "MovieSceneSkeletalAnimationTrack"
        ]
        if len(body_animation_tracks) != 1:
            raise RuntimeError(
                f"Body must contain one baked animation track, found {len(body_animation_tracks)}"
            )

        authored_deltas = list(
            unreal.KairosDemoEditorLibrary.get_body_animation_bone_rotation_deltas(
                self.baked_body_animation,
                start_frame,
                len(frames),
                [unreal.Name(bone) for bone in bones],
            )
        )
        if len(authored_deltas) != len(bones):
            raise RuntimeError("run-owned Body animation bone readback failed")
        authored_max_delta_by_bone_deg = {
            bone: float(value) for bone, value in zip(bones, authored_deltas)
        }
        authored_nonzero_bones = sorted(
            bone
            for bone, value in authored_max_delta_by_bone_deg.items()
            if value > 1e-4
        )
        if set(authored_nonzero_bones) != set(bones):
            raise RuntimeError(
                "run-owned baked Body animation has no authored target-bone motion: "
                f"{authored_max_delta_by_bone_deg}"
            )
        return {
            "enabled": True,
            "implementation": "local-run-owned-baked-body-animsequence",
            "official_nvidia_output": False,
            "coordinate_space": "local-bone-delta-baked-absolute",
            "target_component": "Body",
            "target_bones": bones,
            "bone_weights": weights,
            "track_count": 1,
            "body_animation_tracks": len(body_animation_tracks),
            "key_count": len(frames) * len(bones),
            "source_samples_sha256": source_digest,
            "applied_samples_sha256": digest,
            "render_sync_compensation": compensation,
            "render_sync_calibration": calibration,
            "head_motion_bake": {
                "source_body_animation": self.body_animation.get_path_name(),
                "baked_body_animation": self.baked_body_animation.get_path_name(),
                "baked_face_animation": self.baked_face_animation.get_path_name(),
                "start_frame": start_frame,
                "sample_count": len(frames),
                "fps": fps,
            },
            "authored_max_delta_by_bone_deg": authored_max_delta_by_bone_deg,
            "authored_nonzero_bones": authored_nonzero_bones,
            "application_verification": "post-render-required",
            "lineage": lineage,
            "face_track_count": 1,
            "fixed_camera": True,
            "camera_transform": "unchanged-run-owned-shot-camera",
            "source_asset_modified": False,
        }

    def create_shot_sequence(self, shot, offset_ticks, use_legacy_camera):
        sequence_name = (
            "FinalSequence"
            if use_legacy_camera
            else "Shot_" + shot["id"].replace("-", "_")
        )
        sequence = self.create_level_sequence(sequence_name)
        fps = int(self.config["fps"])
        frame_count = int(self.config["expected_frames"])
        unreal.MovieSceneSequenceExtensions.set_display_rate(
            sequence, unreal.FrameRate(fps, 1)
        )
        unreal.MovieSceneSequenceExtensions.set_tick_resolution_directly(
            sequence, unreal.FrameRate(TICK_RESOLUTION, 1)
        )
        unreal.MovieSceneSequenceExtensions.set_playback_start(sequence, 0)
        unreal.MovieSceneSequenceExtensions.set_playback_end(sequence, frame_count)

        actor_binding = sequence.add_possessable(self.editor_avatar)
        actor_binding.set_display_name("MetaHuman A2F")
        head_motion_readback = self.apply_head_motion(
            sequence, actor_binding, frame_count, offset_ticks
        )
        face_binding = sequence.add_possessable(self.editor_face)
        face_binding.set_display_name("MetaHuman Face")
        face_binding.set_parent(actor_binding)
        animation_track = face_binding.add_track(
            unreal.MovieSceneSkeletalAnimationTrack
        )
        animation_section = animation_track.add_section()
        animation_section.set_start_frame(0)
        animation_section.set_end_frame(frame_count)
        params = unreal.MovieSceneSkeletalAnimationParams()
        params.set_editor_property("animation", self.face_animation)
        params.set_editor_property(
            "start_frame_offset", unreal.FrameNumber(offset_ticks)
        )
        params.set_editor_property("force_custom_mode", True)
        animation_section.set_editor_property("params", params)
        skeletal_tracks = [
            track
            for track in face_binding.get_tracks()
            if track.get_class().get_name() == "MovieSceneSkeletalAnimationTrack"
        ]
        if len(skeletal_tracks) != 1:
            raise RuntimeError(
                f"shot {shot['id']} must contain exactly one face animation track"
            )
        camera_binding, resolved_camera, binding_type = self.add_camera(
            sequence, shot, use_legacy_camera
        )
        camera_binding.set_display_name(f"A2F Camera {shot['id']}")
        camera_track = sequence.add_track(unreal.MovieSceneCameraCutTrack)
        camera_section = camera_track.add_section()
        camera_section.set_start_frame(0)
        camera_section.set_end_frame(frame_count)
        camera_id = unreal.MovieSceneObjectBindingID()
        camera_id.set_editor_property("Guid", camera_binding.get_id())
        camera_section.set_editor_property("CameraBindingID", camera_id)
        if not unreal.EditorAssetLibrary.save_loaded_asset(
            sequence, only_if_is_dirty=False
        ):
            raise RuntimeError(f"failed to save shot LevelSequence {shot['id']}")
        return sequence, {
            "id": shot["id"],
            "preset": shot.get("preset"),
            "camera": resolved_camera,
            "camera_binding_type": binding_type,
            "level_sequence": sequence.get_path_name(),
            "face_animation_tracks": len(skeletal_tracks),
            "head_motion": head_motion_readback,
        }

    def create_final_sequence(self):
        self.face_animation = self.find_face_animation()
        if self.face_animation is None:
            raise RuntimeError("recorded Face AnimSequence was not found")
        self.pre_transform_face_animation = self.face_animation
        duration = float(self.config["audio_duration_seconds"])
        offset = self.animation_started_at - self.take_started_at
        if float(self.face_animation.get_play_length()) + 0.05 < offset + duration:
            raise RuntimeError("recorded Face AnimSequence is shorter than the audio window")
        offset_ticks = round(offset * TICK_RESOLUTION)
        self.face_curve_motion = self.validate_face_curve_motion(offset, duration)
        self.curve_application = self.bake_effective_animation(offset)
        sequence_offset = float(
            self.curve_application.get("sequence_start_offset_seconds", offset)
        )
        validation_offset = float(
            self.curve_application.get("validation_window_offset_seconds", offset)
        )
        self.post_transform_curve_motion = self.validate_face_curve_motion(
            validation_offset, duration
        )
        self.aligned_curve_samples = self.sample_aligned_curves(validation_offset)
        sequence_offset_ticks = round(sequence_offset * TICK_RESOLUTION)
        shots = self.config.get("shots") or [
            {
                "id": "close-up-front",
                "preset": "close-up-front",
                "camera": {
                    "coordinate_space": "avatar_head",
                    "mode": "orbit",
                    "distance_cm": 96.4,
                    "azimuth_deg": 0.0,
                    "elevation_deg": -4.0,
                    "focal_length_mm": 40.0,
                    "aperture": 16.0,
                    "focus_distance_cm": 96.4,
                },
            }
        ]
        use_legacy = (
            len(shots) == 1
            and shots[0]["id"] == "close-up-front"
            and self.avatar_info["object_path"]
            == "/Game/MetaHumans/Taro/BP_Taro.BP_Taro"
        )
        self.shot_sequences = []
        for shot in shots:
            sequence, result = self.create_shot_sequence(
                shot,
                sequence_offset_ticks,
                use_legacy and shot["id"] == "close-up-front",
            )
            self.shot_sequences.append(result)
            if self.final_sequence is None:
                self.final_sequence = sequence

        self.done = True
        unreal.unregister_slate_post_tick_callback(self.tick_handle)
        self.tick_handle = None
        self.write_status(
            "success",
            "capture_complete",
            capture_sequence=self.capture_sequence.get_path_name(),
            final_sequence=self.final_sequence.get_path_name(),
            face_animation=self.face_animation.get_path_name(),
            capture_offset_seconds=offset,
            capture_offset_ticks=offset_ticks,
            sequence_start_offset_seconds=sequence_offset,
            offset_ticks=sequence_offset_ticks,
            captured_animation_seconds=self.animation_ended_at
            - self.animation_started_at,
            face_curve_motion=self.face_curve_motion,
            pre_transform_face_animation=self.pre_transform_face_animation.get_path_name(),
            curve_application=self.curve_application,
            post_transform_curve_motion=self.post_transform_curve_motion,
            aligned_curve_samples=self.aligned_curve_samples,
            ace_blendshape_override_nodes=self.ace_blendshape_override_nodes,
            ace_runtime_curve_parameters=self.config.get(
                "ace_runtime_parameters", {}
            ).get("curve_parameters", {}),
            avatar=self.avatar_info,
            map_path=self.run_map_path,
            shots=self.shot_sequences,
            lineage=self.config.get("lineage"),
        )
        unreal.log(
            f"{LOG_PREFIX} capture complete shots={len(self.shot_sequences)}"
        )

    def tick(self, _delta_seconds):
        if self.done:
            return
        try:
            if time.monotonic() > self.deadline:
                raise RuntimeError(f"timeout in phase {self.phase}")
            if self.phase == "setup":
                self.setup_take_recorder()
            elif self.phase == "wait_pie" and self.level_editor.is_in_play_in_editor():
                self.start_recording()
            elif (
                self.phase == "wait_recorder_state_started"
                and self.take.get_state() == unreal.TakeRecorderState.STARTED
            ):
                self.request_a2f()
            elif self.phase == "wait_pie_end" and not self.level_editor.is_in_play_in_editor():
                self.phase = "build_final_sequence"
                self.deadline = time.monotonic() + 60.0
                self.write_status("running", "build_final_sequence")
                self.create_final_sequence()
        except Exception as exc:
            self.fail(self.phase, exc)


def start_from_environment():
    config_path = os.environ.get("A2F_METAHUMAN_CAPTURE_CONFIG") or os.environ.get(
        "A2F_TARO_CAPTURE_CONFIG"
    )
    if not config_path:
        return None
    return A2FMetaHumanCapture(config_path)
