# -*- coding: utf-8 -*-
"""跑项目标准库 unittest（等价 python -m unittest discover -s tests -v）。

原因：部分受限环境不允许 python -m，用脚本方式等价执行：
    python tools/run_project_tests.py
"""
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

if __name__ == "__main__":
    suite = unittest.TestLoader().discover(
        start_dir=os.path.join(_ROOT, "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
