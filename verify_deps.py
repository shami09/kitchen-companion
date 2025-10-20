import importlib

pkgs = [
    ("livekit.agents", None),
    ("livekit.plugins.openai", None),
    ("dotenv", None),
    ("requests", None),
    ("geopy", None),
    ("langchain", None),
    ("langchain_community", None),
    ("langchain_openai", None),
    ("faiss", None),  # faiss-cpu
    ("pypdf", None),
    ("tiktoken", None),
    ("openai", None),
]

def version(mod):
    for attr in ("__version__", "version", "VERSION"):
        v = getattr(mod, attr, None)
        if isinstance(v, (str, bytes)):
            return v
    return "unknown"

fail = False
for name, _ in pkgs:
    try:
        mod = importlib.import_module(name)
        print(f"{name}: {version(mod)}")
    except Exception as e:
        print(f"[MISSING/ERROR] {name}: {e}")
        fail = True

if fail:
    raise SystemExit(1)
print("✅ All imports ok.")
