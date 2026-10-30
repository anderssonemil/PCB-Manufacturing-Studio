import zipfile
import pytest
from pcb_isolator.review_zip import save_router_review_zip


def test_zip_shares_exact_html_without_machine_files(tmp_path):
    source=tmp_path/'Review.html';content='<html><script>const status="DRAFT";</script>paper check</html>'.encode()
    source.write_bytes(content);(tmp_path/'machine.mmg').write_text('not for sharing')
    result=save_router_review_zip(source,tmp_path/'shared')
    assert result.name=='shared.zip' and source.read_bytes()==content
    with zipfile.ZipFile(result) as z:
        assert set(z.namelist())=={'Router Review.html','READ ME.txt'}
        assert z.read('Router Review.html')==content
        assert 'no CNC' in z.read('READ ME.txt').decode()
        assert z.testzip() is None
    assert not list(tmp_path.glob('*.tmp'))


def test_missing_review_does_not_create_zip(tmp_path):
    with pytest.raises(ValueError,match='Generate'):save_router_review_zip(tmp_path/'missing.html',tmp_path/'share.zip')
    assert not (tmp_path/'share.zip').exists()
