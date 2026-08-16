"""Provider-agnostic file storage seam (M6).

The :class:`~app.services.files.storage.base.FileStorage` protocol is the only
contract the service layer depends on; concrete backends (local filesystem
today; R2 / S3 later) are selected by
:func:`~app.services.files.storage.factory.get_file_storage`. No vendor lock-in
at the interface (CONVENTIONS §6: clean, swappable seams).
"""
