"""Named MCP skill tools generated from trusted registry models, never source code."""
import inspect
from pydantic import create_model


def set_tool_parameters(server, name, parameters):
    """Use one authoritative strict model for both discovery and MCP validation."""
    from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase, FuncMetadata

    class StrictMetadata(FuncMetadata):
        def pre_parse_json(self, data):
            # MCP already carries JSON. Never reinterpret strings as arrays/booleans.
            return data

    tool = server._tool_manager.get_tool(name)
    model = create_model(name + '_Arguments', __base__=(parameters, ArgModelBase))
    tool.parameters = parameters.model_json_schema()
    tool.fn_metadata = StrictMetadata(arg_model=model)


def register_skill_tools(server, registry, start, lock, *, prefix='skill_', asynchronous=False):
    for row in registry.describe():
        definition = registry._definitions[row['name']]
        name = prefix + definition.name
        if server._tool_manager.get_tool(name) is not None:
            raise ValueError('Skill tool name collision')

        def make(definition):
            def invoke(**parameters):
                registry.prepare(definition.name, parameters)
                with lock:
                    return start(definition.name, parameters)
            if asynchronous:
                async def invoke(**parameters):
                    registry.prepare(definition.name, parameters)
                    return await start(definition.name, parameters)
            invoke.__name__ = prefix + definition.name
            invoke.__doc__ = (definition.description +
                (' Returns admission, not gameplay success. Read events/task_result. Use interrupt for cancellation; no automatic resume.' if asynchronous else
                 ' Returns a background job receipt, not goal success. Poll skill_status; cancel_skill requests cleanup. Never retry uncertain effects. Parameters are native world coordinates where applicable, not BCL modal coordinates.'))
            invoke.__signature__ = inspect.Signature([
                inspect.Parameter(field, inspect.Parameter.KEYWORD_ONLY,
                                  annotation=info.annotation,
                                  default=inspect.Parameter.empty if info.is_required() else info.default)
                for field, info in definition.parameters.model_fields.items()],
                return_annotation=dict)
            return invoke

        fn = make(definition)
        server.add_tool(fn, name=name)
        # Preserve the actual model's strictness, bounds and cross-field validators.
        set_tool_parameters(server, name, definition.parameters)
