import cuopt

print("=== cuOpt top-level modules ===")
modules = [x for x in dir(cuopt) if not x.startswith("_")]
print(modules)
print()

for mod_name in modules:
    try:
        mod = getattr(cuopt, mod_name)
        if hasattr(mod, "__file__") or hasattr(mod, "__path__"):
            print(f"\n=== cuopt.{mod_name} ===")
            submodules = [x for x in dir(mod) if not x.startswith("_")]
            print(submodules[:30])  # First 30 items
    except Exception as e:
        print(f"{mod_name}: {e}")
