"""Inspect real Windows cache DACLs independently of the ctypes implementation."""

import json
import os
import sqlite3
import subprocess

import pytest

from hoi4cm.mod import scan_cache as sc

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows DACL integration")


def _powershell(script, path):
    env = dict(os.environ, HOI4CM_ACL_TEST_PATH=str(path))
    # The calling shell may be PowerShell 7; let Windows PowerShell discover
    # its own built-in modules rather than inheriting an incompatible path.
    env.pop("PSMODULEPATH", None)
    powershell = os.path.join(
        os.environ["SystemRoot"],
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe",
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _acl(path):
    return json.loads(
        _powershell(
            """
            $ErrorActionPreference = 'Stop'
            $acl = Get-Acl -LiteralPath $env:HOI4CM_ACL_TEST_PATH
            $sidType = [System.Security.Principal.SecurityIdentifier]
            $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
            $rules = @($acl.GetAccessRules($true, $true, $sidType) | ForEach-Object {
                @{
                    sid = $_.IdentityReference.Value
                    rights = [int]$_.FileSystemRights
                    type = $_.AccessControlType.ToString()
                    inherited = $_.IsInherited
                    inheritance = [int]$_.InheritanceFlags
                }
            })
            @{
                protected = $acl.AreAccessRulesProtected
                user = $user
                rules = $rules
            } | ConvertTo-Json -Depth 4 -Compress
            """,
            path,
        )
    )


@pytest.mark.parametrize("preexisting", [False, True])
def test_windows_cache_dacl_is_private(tmp_path, monkeypatch, preexisting):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(sc, "STATE_DIR", str(state_dir))
    mod_root = str(tmp_path / "mod")
    cache_dir = state_dir / "scan_cache"
    database = sc.database_path(mod_root)

    # Deliberately broad inherited permissions, plus an explicit old-directory
    # grant, prove that chmod/exist_ok cannot accidentally pass this test.
    _powershell(
        """
        $ErrorActionPreference = 'Stop'
        $path = $env:HOI4CM_ACL_TEST_PATH
        $acl = Get-Acl -LiteralPath $path
        $everyone = [System.Security.Principal.SecurityIdentifier]::new('S-1-1-0')
        $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
            $everyone, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $path -AclObject $acl
        """,
        state_dir,
    )
    if preexisting:
        cache_dir.mkdir()
        _powershell(
            """
            $ErrorActionPreference = 'Stop'
            $path = $env:HOI4CM_ACL_TEST_PATH
            $acl = Get-Acl -LiteralPath $path
            $everyone = [System.Security.Principal.SecurityIdentifier]::new('S-1-1-0')
            $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
                $everyone, 'FullControl', 'ContainerInherit,ObjectInherit',
                'None', 'Allow')
            $acl.AddAccessRule($rule)
            Set-Acl -LiteralPath $path -AclObject $acl
            """,
            cache_dir,
        )
        with sqlite3.connect(database) as conn:
            conn.execute(sc._SCHEMA)
            conn.execute(
                "INSERT INTO file_cache VALUES (?, ?, ?, ?, ?)",
                ("focus", "/old.txt", 1.0, 1, '["OLD"]'),
            )
        before = _acl(cache_dir)
        assert any(rule["sid"] == "S-1-1-0" for rule in before["rules"])
        assert any(rule["sid"] == "S-1-1-0" for rule in _acl(database)["rules"])

    cache = sc.ScanCache(mod_root)
    try:
        assert cache.enabled
        if preexisting:
            assert cache.get("focus", "/old.txt", 1.0, 1) == ["OLD"]
        for path in (cache_dir, database):
            acl = _acl(path)
            assert len(acl["rules"]) == 1
            rule = acl["rules"][0]
            assert rule["sid"] == acl["user"]
            assert rule["type"] == "Allow"
            assert rule["rights"] == 0x1F01FF  # FILE_ALL_ACCESS
            if path == cache_dir:
                assert acl["protected"]
                assert not rule["inherited"]
                assert rule["inheritance"] == 3  # ContainerInherit | ObjectInherit
            else:
                assert rule["inherited"]
    finally:
        cache.close()
