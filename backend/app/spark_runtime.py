import os
from pathlib import Path


def configure_spark_java() -> None:
    configured_home = os.getenv("SPARK_JAVA_HOME")
    if not configured_home:
        return

    java_home = Path(configured_home).expanduser().resolve()
    executable = java_home / "bin" / ("java.exe" if os.name == "nt" else "java")
    if not executable.is_file():
        raise RuntimeError("SPARK_JAVA_HOME does not contain a Java executable")

    os.environ["JAVA_HOME"] = str(java_home)
    java_bin = str(executable.parent)
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if not path_entries or os.path.normcase(path_entries[0]) != os.path.normcase(java_bin):
        os.environ["PATH"] = os.pathsep.join([java_bin, *path_entries])
