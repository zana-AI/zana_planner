import inspect
from typing import get_type_hints, Optional, Dict, Any


def get_function_args_info(func: Any) -> Dict[str, Optional[type]]:
    """
    Retrieves the names and types of arguments of the given function.

    Args:
        func (callable): The function to inspect.

    Returns:
        Dict[str, Optional[type]]: A dictionary mapping argument names to their types.
                                   If a type hint is missing, the value is None.
    """
    # Retrieve the signature of the function
    signature = inspect.signature(func)

    # Retrieve type hints (annotations) of the function
    type_hints = get_type_hints(func)

    args_info = {}
    for name, param in signature.parameters.items():
        if name in ["self", "user_id"]:
            continue
        # Skip variable-length arguments for now
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        # Get the type hint if available
        arg_type = type_hints.get(name, None)
        args_info[name] = arg_type

    return args_info