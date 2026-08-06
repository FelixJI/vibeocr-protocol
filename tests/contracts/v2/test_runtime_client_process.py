from __future__ import annotations

import ctypes
import io
import json
import subprocess
from unittest.mock import Mock, call

import pytest
import vibeocr.runtime_client.job_object as job_object_module
import vibeocr.runtime_client.process as process_module
from vibeocr.runtime_client.job_object import JobObjectGuard
from vibeocr.runtime_client.process import SupervisorLaunchError, SupervisorProcess


def test_job_object_guard_is_a_noop_outside_windows(monkeypatch) -> None:
    get_kernel32 = Mock()
    monkeypatch.setattr(job_object_module, "_IS_WINDOWS", False)
    monkeypatch.setattr(job_object_module, "_get_kernel32", get_kernel32)
    popen = Mock(pid=1234)

    with JobObjectGuard() as guard:
        assert guard.assign_from_popen(popen) is False
    guard.close()

    get_kernel32.assert_not_called()


def test_job_object_guard_assigns_process_to_kill_on_close_job(monkeypatch) -> None:
    captured_flags: list[int] = []
    kernel32 = Mock()
    kernel32.CreateJobObjectW.return_value = 101
    kernel32.OpenProcess.return_value = 202
    kernel32.AssignProcessToJobObject.return_value = 1

    def capture_limits(
        _job_handle: int,
        _info_class: int,
        info_pointer,
        _info_size: int,
    ) -> int:
        info = ctypes.cast(
            info_pointer,
            ctypes.POINTER(job_object_module.JOBOBJECT_EXTENDED_LIMIT_INFORMATION),
        ).contents
        captured_flags.append(info.BasicLimitInformation.LimitFlags)
        return 1

    kernel32.SetInformationJobObject.side_effect = capture_limits
    monkeypatch.setattr(job_object_module, "_IS_WINDOWS", True)
    monkeypatch.setattr(job_object_module, "_get_kernel32", lambda: kernel32)
    popen = Mock(pid=4321)

    guard = JobObjectGuard(name="runtime-client-test")
    assert guard.assign_from_popen(popen) is True
    guard.close()
    guard.close()

    assert captured_flags == [
        job_object_module.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | job_object_module.JOB_OBJECT_LIMIT_BREAKAWAY_OK
    ]
    assert kernel32.CreateJobObjectW.call_args.args[1].value == "runtime-client-test"
    kernel32.AssignProcessToJobObject.assert_called_once_with(101, 202)
    assert kernel32.CloseHandle.call_args_list == [call(202), call(101)]


def test_job_object_guard_degrades_when_windows_job_setup_fails(monkeypatch) -> None:
    kernel32 = Mock()
    kernel32.CreateJobObjectW.return_value = 101
    kernel32.SetInformationJobObject.return_value = 0
    monkeypatch.setattr(job_object_module, "_IS_WINDOWS", True)
    monkeypatch.setattr(job_object_module, "_get_kernel32", lambda: kernel32)

    guard = JobObjectGuard()

    assert guard.assign_from_popen(Mock(pid=4321)) is False
    kernel32.CloseHandle.assert_called_once_with(101)
    kernel32.OpenProcess.assert_not_called()


def _ready_line(*, pid: int = 4321, port: int = 54321) -> str:
    return (
        json.dumps(
            {
                "ready": True,
                "pid": pid,
                "port": port,
                "instance_id": "supervisor-test",
                "protocol_version": process_module.PROTOCOL_VERSION,
                "schema_version": process_module.SCHEMA_VERSION,
                "capabilities": ["ocr.recognition.v2"],
                "ready_version": process_module.READY_ENVELOPE_VERSION,
            }
        )
        + "\n"
    )


def _fake_popen(stdout_line: str) -> Mock:
    popen = Mock()
    popen.pid = 4321
    popen.stdout = io.StringIO(stdout_line)
    popen.stderr = io.StringIO("")
    popen.wait.return_value = 0
    return popen


def test_supervisor_process_launches_ready_and_shuts_down_owned_process(
    monkeypatch,
) -> None:
    popen = _fake_popen(_ready_line())
    popen_factory = Mock(return_value=popen)
    guard = Mock()
    guard_factory = Mock(return_value=guard)
    threads = [Mock(), Mock()]
    thread_factory = Mock(side_effect=threads)
    monkeypatch.setattr(process_module, "generate_token", lambda: "session-token")
    monkeypatch.setattr(process_module.subprocess, "Popen", popen_factory)
    monkeypatch.setattr(process_module, "JobObjectGuard", guard_factory)
    monkeypatch.setattr(process_module.threading, "Thread", thread_factory)

    owner = SupervisorProcess.launch(
        python_exe="python.exe",
        module="fake.supervisor",
        startup_timeout=0.1,
        extra_env={"RUNTIME_TEST": "enabled"},
        working_directory="C:/runtime",
    )

    command = popen_factory.call_args.args[0]
    options = popen_factory.call_args.kwargs
    assert command == ["python.exe", "-m", "fake.supervisor"]
    assert "session-token" not in command
    assert options["env"]["VIBEOCR_SUP_TOKEN"] == "session-token"
    assert options["env"]["RUNTIME_TEST"] == "enabled"
    assert options["env"]["PYTHONIOENCODING"] == "utf-8"
    assert options["env"]["PYTHONUTF8"] == "1"
    assert options["cwd"] == "C:/runtime"
    assert owner.base_url == "http://127.0.0.1:54321"
    assert owner.session_token == "session-token"
    assert owner.pid == 4321
    guard.assign_from_popen.assert_called_once_with(popen)
    assert [thread.start.call_count for thread in threads] == [1, 1]

    assert owner.shutdown(timeout=0.25) == 0
    assert owner.shutdown(timeout=0.25) == 0
    popen.terminate.assert_called_once_with()
    popen.wait.assert_called_once_with(timeout=0.25)
    guard.close.assert_called_once_with()


def test_supervisor_process_kills_child_after_graceful_shutdown_timeout() -> None:
    popen = Mock()
    popen.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="fake.supervisor", timeout=0.1),
        137,
    ]
    guard = Mock()
    owner = SupervisorProcess(
        python_exe="python.exe",
        _proc=popen,
        _job_guard=guard,
    )

    assert owner.shutdown(timeout=0.1) == 137

    popen.terminate.assert_called_once_with()
    popen.kill.assert_called_once_with()
    assert popen.wait.call_args_list == [call(timeout=0.1), call(timeout=0.1)]
    guard.close.assert_called_once_with()


def test_supervisor_process_cleans_up_invalid_ready_launch(monkeypatch) -> None:
    popen = _fake_popen("not-json\n")
    guard = Mock()
    threads = [Mock(), Mock()]
    monkeypatch.setattr(process_module.subprocess, "Popen", Mock(return_value=popen))
    monkeypatch.setattr(process_module, "JobObjectGuard", Mock(return_value=guard))
    monkeypatch.setattr(
        process_module.threading,
        "Thread",
        Mock(side_effect=threads),
    )

    with pytest.raises(SupervisorLaunchError, match="invalid ready envelope"):
        SupervisorProcess.launch(python_exe="python.exe", module="fake.supervisor")

    popen.terminate.assert_called_once_with()
    popen.wait.assert_called_once_with(timeout=5.0)
    guard.close.assert_called_once_with()
