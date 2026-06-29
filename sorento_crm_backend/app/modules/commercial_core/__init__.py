"""Commercial core module package.

On import, ensures any reciprocal relationships this module declares onto base
platform classes (Customer, WorkflowStage, RespondWorkspace, RespondContact)
exist — adding them lazily for codebases that didn't ship the patches.
Without this, uploading commercial_core to a fresh deployment poisons the
SQLAlchemy mapper registry because ``back_populates="..."`` strings resolve
to properties that don't exist on the platform side.
"""
from app.modules.commercial_core import models as _models  # noqa: F401  ensure mappers exist
from app.modules.commercial_core import models_process_config as _models_pc  # noqa: F401
from app.modules.commercial_core import models_quotation_email_template as _models_qet  # noqa: F401
from app.modules.commercial_core._base_patches import apply_base_patches as _apply_base_patches

_apply_base_patches()
