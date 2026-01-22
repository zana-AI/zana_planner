# Subtask Feature Documentation

## Overview

The subtask feature enables hierarchical organization of tasks/promises in the Zana Planner system. Users can now create parent-child relationships between promises, allowing for better project management and task organization.

## Database Schema Changes

### Migration: 007_add_subtasks

A new column `parent_promise_uuid` has been added to the `promises` table:

- **Column**: `parent_promise_uuid` (TEXT, nullable)
- **Foreign Key**: References `promises.promise_uuid` with `ON DELETE SET NULL`
- **Index**: Created on `parent_promise_uuid` for efficient subtask queries

If a parent promise is deleted, all child promises will have their `parent_promise_uuid` set to NULL automatically.

## Model Changes

### Promise Model (`models/models.py`)

The `Promise` dataclass now includes:

```python
parent_id: Optional[str] = None  # ID of parent promise (for subtasks)
```

This field stores the user-facing ID (e.g., "PROJECT01") of the parent promise, not the internal UUID.

## Repository API

### PromisesRepository (`repositories/promises_repo.py`)

#### Modified Methods

1. **`list_promises(user_id: int, parent_id: Optional[str] = None) -> List[Promise]`**
   - Now accepts optional `parent_id` parameter
   - If `parent_id` is provided, returns only direct children of that parent
   - If `parent_id` is None (default), returns all promises regardless of hierarchy
   - All returned promises include their `parent_id` field populated

2. **`get_promise(user_id: int, promise_id: str) -> Optional[Promise]`**
   - Returns promise with `parent_id` field populated
   - Automatically resolves parent's UUID to user-facing ID

3. **`upsert_promise(user_id: int, promise: Promise) -> None`**
   - Now handles `parent_id` field from the Promise object
   - Validates that parent promise exists before creating/updating
   - Raises `ValueError` if parent promise is not found

#### New Methods

1. **`get_subtasks(user_id: int, parent_id: str) -> List[Promise]`**
   - Convenience method to get all direct children of a parent promise
   - Equivalent to `list_promises(user_id, parent_id=parent_id)`

2. **`has_subtasks(user_id: int, promise_id: str) -> bool`**
   - Check if a promise has any subtasks
   - Returns True if at least one active (non-deleted) subtask exists
   - Returns False otherwise

## Usage Examples

### Creating a Project with Subtasks

```python
from models.models import Promise
from repositories.promises_repo import PromisesRepository

repo = PromisesRepository()
user_id = 12345

# Create parent project
project = Promise(
    user_id=str(user_id),
    id="PROJECT01",
    text="Website_Redesign",
    hours_per_week=20.0,
    recurring=True
)
repo.upsert_promise(user_id, project)

# Create subtasks
subtask1 = Promise(
    user_id=str(user_id),
    id="TASK01",
    text="Design_Mockups",
    hours_per_week=5.0,
    recurring=True,
    parent_id="PROJECT01"  # Link to parent
)
repo.upsert_promise(user_id, subtask1)

subtask2 = Promise(
    user_id=str(user_id),
    id="TASK02",
    text="Frontend_Development",
    hours_per_week=10.0,
    recurring=True,
    parent_id="PROJECT01"  # Link to parent
)
repo.upsert_promise(user_id, subtask2)
```

### Querying Subtasks

```python
# Get all subtasks of a project
subtasks = repo.get_subtasks(user_id, "PROJECT01")
print(f"Found {len(subtasks)} subtasks")

# Check if a promise has subtasks
if repo.has_subtasks(user_id, "PROJECT01"):
    print("This project has subtasks")

# Get all promises (top-level and subtasks)
all_promises = repo.list_promises(user_id)

# Get only top-level promises (no parent)
# Note: This requires filtering client-side currently
top_level = [p for p in all_promises if p.parent_id is None]
```

### Nested Hierarchies

The system supports arbitrary nesting levels:

```python
# Level 1: Project
project = Promise(user_id=str(user_id), id="PROJ", text="Main_Project", hours_per_week=40.0, recurring=True)
repo.upsert_promise(user_id, project)

# Level 2: Phase
phase = Promise(user_id=str(user_id), id="PHASE1", text="Planning_Phase", hours_per_week=20.0, recurring=True, parent_id="PROJ")
repo.upsert_promise(user_id, phase)

# Level 3: Task
task = Promise(user_id=str(user_id), id="TASK1", text="Requirements_Gathering", hours_per_week=10.0, recurring=True, parent_id="PHASE1")
repo.upsert_promise(user_id, task)
```

### Moving Subtasks

To move a subtask to a different parent, simply update its `parent_id`:

```python
# Get the subtask
subtask = repo.get_promise(user_id, "TASK01")

# Change its parent
subtask.parent_id = "PROJECT02"

# Save the update
repo.upsert_promise(user_id, subtask)
```

### Making a Subtask Top-Level

To convert a subtask to a top-level promise:

```python
subtask = repo.get_promise(user_id, "TASK01")
subtask.parent_id = None
repo.upsert_promise(user_id, subtask)
```

## API Impact

The web API endpoints that return promises (e.g., `/promises`, `/promises/{id}`) will now include the `parent_id` field in the JSON response when it's set.

Example response:
```json
{
  "id": "TASK01",
  "text": "Design_Mockups",
  "hours_per_week": 5.0,
  "recurring": true,
  "parent_id": "PROJECT01",
  ...
}
```

## Testing

Comprehensive tests have been added in `tests/repositories/test_promises_repo.py`:

- `test_promises_repo_create_subtask` - Creating a subtask with a parent
- `test_promises_repo_list_subtasks` - Listing subtasks of a parent
- `test_promises_repo_has_subtasks` - Checking if a promise has subtasks
- `test_promises_repo_nested_subtasks` - Creating multi-level hierarchies
- `test_promises_repo_update_subtask_parent` - Moving subtasks between parents

## Migration Notes

### Existing Data

Existing promises will have `parent_promise_uuid = NULL`, meaning they are top-level promises with no parent. No data migration is required.

### Backward Compatibility

The changes are fully backward compatible:
- Old code that doesn't use `parent_id` will continue to work
- The field is optional (defaults to None)
- Existing API responses will include the new field, but it will be `null` for top-level promises

## Future Enhancements

Possible future improvements:
- Add a method to get all descendants (not just direct children) recursively
- Add a method to get the full path from root to a specific promise
- Add database constraints to prevent circular references
- Add bulk operations for moving entire subtrees
- Add UI support for visualizing and managing task hierarchies
