import onnxruntime as ort

CPU_ONLY = ["CPUExecutionProvider"]

_warned_no_dml = False


def providers_for(provider: str) -> list[str]:
    global _warned_no_dml
    if provider == "CPU":
        return list(CPU_ONLY)
    if provider == "GPU":
        available = ort.get_available_providers()
        if "DmlExecutionProvider" not in available:
            if not _warned_no_dml:
                _warned_no_dml = True
                print(
                    "DirectML is unavailable on this machine; running the models "
                    f"on the CPU instead. Providers: {available}"
                )
            return list(CPU_ONLY)
        return ["DmlExecutionProvider"] + CPU_ONLY
    raise ValueError(f"Unsupported model provider: {provider}")


def session_options_for(provider: str) -> ort.SessionOptions:
    session_options = ort.SessionOptions()
    session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if provider == "CPU":
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        session_options.intra_op_num_threads = 2
        session_options.inter_op_num_threads = 1
    return session_options
