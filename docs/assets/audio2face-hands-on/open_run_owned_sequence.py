"""Open the verified r7 run-owned map and sequence for a read-only screenshot."""

import unreal


MAP_PATH = "/Game/Maps/TaroA2F/TaroFaceBodyDemo_Repaired"
SEQUENCE_PATH = (
    "/Game/Cinematics/A2FMetaHumanCLI/"
    "20260829_110741_head_motion_sync_final_r7/FinalSequence.FinalSequence"
)


unreal.EditorLoadingAndSavingUtils.load_map(MAP_PATH)
sequence = unreal.load_asset(SEQUENCE_PATH)
if sequence is None:
    raise RuntimeError(f"run-owned LevelSequence is missing: {SEQUENCE_PATH}")
unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(sequence)
unreal.LevelSequenceEditorBlueprintLibrary.set_lock_camera_cut_to_viewport(True)
unreal.LevelSequenceEditorBlueprintLibrary.set_current_time(60)
unreal.log(
    "[A2F-HANDS-ON] opened verified run-owned FinalSequence at display frame 60"
)
