# Vendored Upstream Revisions

The initial repository snapshot consolidates three previously nested Git
repositories into the root repository. Their source files are vendored so that
the workspace, including its local experiments, can be reproduced from one
remote.

| Component | Upstream | Base revision |
| --- | --- | --- |
| OpenFace 3.0 | `https://github.com/CMU-MultiComp-Lab/OpenFace-3.0.git` | `662a555a8566ae3aec8139cb8c72acf6d06e0eb3` |
| Pytorch RetinaFace | `https://github.com/biubug6/Pytorch_Retinaface.git` | `b984b4b775b2c4dced95c1eadd195a5c7d32a60b` |
| STAR | `https://github.com/ZhenglinZhou/STAR.git` | `9b125749b0d35766ed83d047036d1aa5e384984c` |

The vendored tree is not a pristine upstream checkout. It includes local
changes and untracked experiment files that were present when the root
repository was initialized. Downloaded weights, caches, and generated outputs
are excluded by the root `.gitignore`.
