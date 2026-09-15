#!/usr/bin/env python3
"""Validate the quantitative trading system environment and connectivity."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_python_version():
    """Check Python version >= 3.10."""
    import platform
    major, minor, _ = platform.python_version_tuple()
    if (int(major), int(minor)) < (3, 10):
        print(f"[FAIL] Python 3.10+ required, found {platform.python_version()}")
        return False
    print(f"[OK] Python {platform.python_version()}")
    return True


def check_dependencies():
    """Check required packages can be imported."""
    required = [
        "akshare", "backtrader", "pandas", "numpy", "yaml",
        "matplotlib", "sklearn", "joblib", "scipy", "pyarrow", "tqdm",
    ]
    all_ok = True
    for pkg in required:
        try:
            __import__(pkg)
            print(f"[OK] {pkg}")
        except ImportError:
            print(f"[FAIL] {pkg} not installed")
            all_ok = False
    return all_ok


def check_config():
    """Check configuration files exist and are valid YAML."""
    from quantsys.utils.config import load_all_configs

    config_dir = Path(__file__).parent.parent / "config"
    configs = list(config_dir.glob("*.yaml"))
    if not configs:
        print("[FAIL] No config files found in config/")
        return False

    all_ok = True
    for cf in configs:
        try:
            load_all_configs(config_dir)
            print(f"[OK] {cf.name}")
        except Exception as e:
            print(f"[FAIL] {cf.name}: {e}")
            all_ok = False
    return all_ok


def check_data_dirs():
    """Check data directories exist."""
    data_dir = Path(__file__).parent.parent / "data"
    required = ["raw", "processed"]
    all_ok = True
    for d in required:
        p = data_dir / d
        if p.exists():
            print(f"[OK] data/{d}/ exists")
        else:
            print(f"[WARN] data/{d}/ does not exist (will be created on first run)")
    return all_ok


def check_akshare():
    """Check AKShare connectivity."""
    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        if df is not None and not df.empty:
            print(f"[OK] AKShare connected (latest trade date: {df['trade_date'].iloc[-1]})")
            return True
        else:
            print("[FAIL] AKShare returned empty data")
            return False
    except Exception as e:
        print(f"[WARN] AKShare connectivity test failed: {e}")
        return True  # Not critical for setup validation


def main():
    """Run all validation checks."""
    print("=" * 60)
    print("  中国A股量化交易系统 - Environment Validation")
    print("=" * 60)

    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Configuration", check_config),
        ("Data Directories", check_data_dirs),
        ("AKShare Connectivity", check_akshare),
    ]

    results = {}
    for name, check_fn in checks:
        print(f"\n--- {name} ---")
        results[name] = check_fn()

    print("\n" + "=" * 60)
    passed = sum(results.values())
    total = len(results)
    print(f"Results: {passed}/{total} checks passed")

    if passed == total:
        print("All checks passed! System is ready.")
        return 0
    elif all(results.values()):
        print("All critical checks passed.")
        return 0
    else:
        print("Some checks failed. Please fix issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
