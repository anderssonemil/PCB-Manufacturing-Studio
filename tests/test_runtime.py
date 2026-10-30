from pcb_isolator.runtime import machining_path,settings_root


def test_external_settings_initialized_once(tmp_path,monkeypatch):
    monkeypatch.setenv('PCB_ISOLATOR_HOME',str(tmp_path/'user-settings'))
    assert settings_root()==tmp_path/'user-settings'
    path=machining_path()
    assert '[machine]' in path.read_text()
    path.write_text('user settings')
    assert machining_path().read_text()=='user settings'
