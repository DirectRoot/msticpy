# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
"""Azure ML module test."""
import sys
from collections import namedtuple
from pathlib import Path
from typing import Any, Dict

import pytest
import pytest_check as check

from msticpy.init import azure_ml_tools as aml

from ..unit_test_lib import change_directory

__author__ = "Ian Hellen"

# pylint: disable=redefined-outer-name

_MIN_PY_VER = "3.10"
_MIN_MP_VER = "2.0.0"
_MIN_PY_VER_T = (3, 10, 0)
_MIN_MP_VER_T = (2, 0, 0)

_MP_CONFIG = "msticpyconfig-test.yaml"

VersionInfo = namedtuple("VersionInfo", "major, minor, micro, releaselevel, serial")


@pytest.fixture(scope="module")
def aml_file_sys(tmpdir_factory):
    """Create fake aml file system."""
    mp_text = Path("tests").joinpath(_MP_CONFIG).read_text(encoding="utf-8")
    root = tmpdir_factory.mktemp("aml-test")
    users = root.mkdir("Users")
    user_dir = users.mkdir("aml_user")
    user_dir.mkdir("utils")
    user_dir.mkdir("subdir")

    user_dir.join("msticpyconfig.yaml").write_text(mp_text, encoding="utf-8")
    user_dir.join("msticpyconfig.save").write_text(mp_text, encoding="utf-8")
    yield users, user_dir


_CURR_VERSION = [v for v in aml.__version__.split(".") if v.isnumeric()]
_MP_FUT_VER = ".".join(f"{int(v) + 1}" for v in _CURR_VERSION)
_MP_FUT_VER_T = tuple(int(v) + 1 for v in _CURR_VERSION)

_EXP_ENV = {
    "KQLMAGIC_EXTRAS_REQUIRE": "jupyter-basic",
    "KQLMAGIC_AZUREML_COMPUTE": "myhost",
}
_EXP_ENV_JPX = _EXP_ENV.copy()
_EXP_ENV_JPX["KQLMAGIC_EXTRAS_REQUIRE"] = "jupyter-extended"


class _PyOs:
    """Emulation for os package."""

    def __init__(self):
        self.environ: Dict[str, Any] = {}


class _ipython:
    """Emulation for IPython shell."""

    pgo_installed = False

    def run_line_magic(self, *args, **kwargs):
        """Return package list."""
        del kwargs
        if "apt list" in args:
            if self.pgo_installed:
                return ["libgirepository1.0-dev", "gir1.2-secret-1"]
            return []


CheckVers = namedtuple("CheckVers", "py_req, mp_req, extras, is_aml, excep, env")

CHECK_VERS = [
    CheckVers(_MIN_PY_VER, _MIN_MP_VER, None, True, None, _EXP_ENV),
    CheckVers(_MIN_PY_VER, _MIN_MP_VER, ["azsentinel"], True, None, _EXP_ENV_JPX),
    CheckVers("9.9", _MIN_MP_VER, None, True, RuntimeError, _EXP_ENV),
    CheckVers(_MIN_PY_VER, _MP_FUT_VER, None, True, ImportError, _EXP_ENV),
    CheckVers("5.12", _MIN_MP_VER, None, True, RuntimeError, _EXP_ENV),
    # is_aml == False
    CheckVers(_MIN_PY_VER, _MIN_MP_VER, None, False, None, _EXP_ENV),
    CheckVers(_MIN_PY_VER, _MIN_MP_VER, ["azsentinel"], False, None, _EXP_ENV_JPX),
    # Versions as tuples
    CheckVers(_MIN_PY_VER_T, _MIN_MP_VER_T, None, True, None, _EXP_ENV),
    CheckVers(_MIN_PY_VER_T, _MIN_MP_VER_T, ["azsentinel"], True, None, _EXP_ENV_JPX),
    CheckVers((9, 9), _MIN_MP_VER_T, None, True, RuntimeError, _EXP_ENV),
    CheckVers(_MIN_PY_VER_T, _MP_FUT_VER_T, None, True, ImportError, _EXP_ENV),
]


def _test_ids(test_cases):
    for test_case in test_cases:
        yield "-".join(
            f"{key}:{str(val)[:10]}" for key, val in test_case._asdict().items()
        )


@pytest.mark.parametrize("check_vers", CHECK_VERS, ids=_test_ids(CHECK_VERS))
def test_check_versions(monkeypatch, aml_file_sys, check_vers):
    """Test check_versions."""
    _, user_dir = aml_file_sys

    # monkeypatch for various test cases
    _os = _PyOs()
    monkeypatch.setattr(aml, "os", _os)
    monkeypatch.setattr(aml, "get_ipython", _ipython)
    monkeypatch.setattr(aml, "_get_vm_fqdn", lambda: "myhost")
    if sys.version_info[:3] < (3, 10):
        monkeypatch.setattr(sys, "version_info", VersionInfo(3, 10, 0, "final", 0))

    if check_vers.is_aml:
        # Set an env var to emulate AML
        _os.environ["APPSETTING_WEBSITE_SITE_NAME"] = "AMLComputeInstance"

    if check_vers.excep:
        with pytest.raises(check_vers.excep):
            with change_directory(str(user_dir)):
                aml.check_aml_settings(
                    min_py_ver=check_vers.py_req,
                    min_mp_ver=check_vers.mp_req,
                    extras=check_vers.extras,
                )
    else:
        with change_directory(str(user_dir)):
            aml.check_aml_settings(
                min_py_ver=check_vers.py_req,
                min_mp_ver=check_vers.mp_req,
                extras=check_vers.extras,
            )

        env = "KQLMAGIC_EXTRAS_REQUIRE"
        check.is_in(env, _os.environ)
        check.equal(check_vers.env[env], _os.environ.get(env))
        if check_vers.is_aml:
            env = "KQLMAGIC_AZUREML_COMPUTE"
            check.is_in(env, _os.environ)
            check.equal(check_vers.env[env], _os.environ.get(env))


MpConfig = namedtuple("MpConfig", "sub_dir, mpconf_exists")
_MP_CONFIG_TESTS = [
    MpConfig(False, True),
    MpConfig(False, False),
    MpConfig(True, True),
    MpConfig(True, False),
]


@pytest.mark.parametrize("test_case", _MP_CONFIG_TESTS, ids=_test_ids(_MP_CONFIG_TESTS))
def test_check_versions_mpconfig(monkeypatch, aml_file_sys, test_case):
    """Test check_versions."""
    _, user_dir = aml_file_sys
    mp_path = user_dir.join("msticpyconfig.yaml")
    mp_backup = user_dir.join("msticpyconfig.save")

    target_dir = user_dir.join("subdir") if test_case.sub_dir else user_dir

    if not test_case.mpconf_exists:
        mp_path.remove(ignore_errors=True)

    # monkeypatch for various test cases
    _os = _PyOs()
    monkeypatch.setattr(aml, "os", _os)
    monkeypatch.setattr(aml, "_get_vm_fqdn", lambda: "myhost")
    if sys.version_info[:3] < (3, 10):
        monkeypatch.setattr(sys, "version_info", VersionInfo(3, 10, 0, "final", 0))

    # Set an env var to emulate AML
    _os.environ["APPSETTING_WEBSITE_SITE_NAME"] = "AMLComputeInstance"

    with change_directory(str(target_dir)):
        aml.check_aml_settings(min_py_ver=_MIN_PY_VER, min_mp_ver=_MIN_MP_VER)

    if test_case.sub_dir and test_case.mpconf_exists:
        env = "MSTICPYCONFIG"
        check.is_in(env, _os.environ)
        check.is_true(mp_path.samefile(_os.environ.get(env)))
    mp_backup.copy(mp_path)
