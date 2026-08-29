# Unreal helper source mirrors

This directory keeps the reviewable source mirrors for helpers deployed into the
project-local KairosSample installation:

```text
a2f_metahuman_capture.py    -> .tools/audio2face-metahuman/KairosSample/Content/Python/a2f_metahuman_capture.py
KairosDemoEditorLibrary.h   -> .tools/audio2face-metahuman/KairosSample/Source/KairosSample/Public/KairosDemoEditorLibrary.h
KairosDemoEditorLibrary.cpp -> .tools/audio2face-metahuman/KairosSample/Source/KairosSample/Private/KairosDemoEditorLibrary.cpp
```

The project-local `.tools` installation is intentionally ignored by Git. Keep each
mirror byte-identical with its deployed counterpart before UE build, validation,
and Gate 2 review.
