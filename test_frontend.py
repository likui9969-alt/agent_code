"""Quick test for all new frontend modules."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ["REDIS_ENABLED"] = "false"

from frontend.i18n import t
from frontend.services.history_store import get_history_store
from frontend.services.file_manager import get_file_manager

print("=== i18n ===")
print(f"  new_chat: {t('new_chat').encode('utf-8')}")
print(f"  approve: OK (len={len(t('approve'))})")
print(f"  settings: OK (len={len(t('settings'))})")

print("\n=== History Store ===")
store = get_history_store()
cid = store.create_chat("test")
print(f"  created: {cid}")
store.rename_chat(cid, "renamed")
chat = store.get_chat(cid)
print(f"  renamed to: {chat['title']}")
store.delete_chat(cid)
print("  deleted: OK")

print("\n=== File Manager ===")
fm = get_file_manager()
print(f"  is_open: {fm.is_open()}")

print("\n=== Imports ===")
from frontend.components.project_explorer import render_project_explorer
from frontend.components.chat_history import render_chat_history
from frontend.components.editor_tabs import render_editor_tabs
from frontend.components.file_operations import render_apply_code_panel
print("  all component imports OK")

print("\nAll frontend tests passed!")
