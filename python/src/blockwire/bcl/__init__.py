"""BCL/1 offline compiler and declarative capability discovery.

Execution is explicit: import BCLRunner/BCLJobs from blockwire.bcl.runtime.
No source is evaluated, and importing/compiling never contacts Minecraft.
"""
from .compiler import BCLError,Diagnostic,Program,Operation,Binding,compile_bcl,compile_report
from .registry import VERSION,Parameter,Command,CommandRegistry,default_commands,DEFAULT_PERMISSIONS

__all__=['BCLError','Diagnostic','Program','Operation','Binding','compile_bcl','compile_report',
         'VERSION','Parameter','Command','CommandRegistry','default_commands','DEFAULT_PERMISSIONS']
