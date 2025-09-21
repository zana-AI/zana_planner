# Schema Conflict Fix

## ✅ Issue Identified and Resolved

### **Problem**
There was a naming conflict between:
- `tm_bot/schema/` (folder containing models and enums)
- `tm_bot/schema.py` (file containing LLMResponse and legacy classes)

This conflict would cause Python import issues when trying to import from either the folder or the file.

### **Solution**
Renamed the folder from `schema/` to `models/` to eliminate the conflict:
- `tm_bot/schema/` → `tm_bot/models/`
- `tm_bot/schema.py` remains unchanged (contains LLMResponse and legacy UserAction)

### **Files Updated**
Updated all import statements in the following files:
- `tm_bot/repositories/sessions_repo.py`
- `tm_bot/services/planner_api_adapter.py`
- `tm_bot/services/sessions.py`
- `tm_bot/services/reminders.py`
- `tm_bot/services/ranking.py`
- `tm_bot/ui/keyboards.py`
- `tm_bot/ui/messages.py`
- `tm_bot/repositories/settings_repo.py`
- `tm_bot/repositories/actions_repo.py`
- `tm_bot/repositories/promises_repo.py`

### **Import Changes**
All imports changed from:
```python
from ..schema.models import ModelName
from ..schema.enums import EnumName
```

To:
```python
from ..models.models import ModelName
from ..models.enums import EnumName
```

### **Documentation Updated**
Updated references in:
- `REFACTOR_SUMMARY.md`
- `CLEANUP_SUMMARY.md`

### **Final Structure**
```
tm_bot/
├── models/                    # Data models folder (renamed from schema/)
│   ├── __init__.py
│   ├── models.py             # Promise, Action, UserSettings, Session
│   └── enums.py              # ActionType, SessionStatus, Weekday
├── schema.py                 # LLMResponse and legacy UserAction
└── ... (other files)
```

### **Verification**
- ✅ No import conflicts
- ✅ All imports resolve correctly
- ✅ No linting errors (only expected external dependency warnings)
- ✅ Folder structure is clean and logical

The naming conflict has been completely resolved, and the codebase now has a clear separation between the data models folder (`models/`) and the schema file (`schema.py`).
