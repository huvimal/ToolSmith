"""Actual Streamlit runner -> SDK client -> stdio server -> isolated SQLite state."""
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from domain import ROOT,Store


def click(app,label):
    next(b for b in app.button if b.label==label).click().run(timeout=60)
    assert not app.exception,list(app.exception)


if __name__=='__main__':
    (ROOT/'reports').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='toolsmith-ui-') as temp:
        db=Path(temp)/'ui.db'
        with patch.dict(os.environ,{'TOOLSMITH_DB':str(db)}):
            store=Store(db)
            app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run()
            assert not app.exception and not app.error
            click(app,'Connect and inspect MCP')
            assert len(app.session_state['inspection']['tools'])==10
            click(app,'Search documents via MCP')
            assert not app.session_state['last_result']['is_error']
            click(app,'Read document via MCP')
            assert app.session_state['last_result']['data']['path']=='retries.md'
            click(app,'Create proposal via MCP')
            click(app,'Create proposal via MCP')
            assert len(store.pending())==1 and store.issue('ALPHA-001')['version']==1
            approval_button=next(b for b in app.button if b.label=='Approve exact proposal locally')
            assert approval_button.disabled
            app.checkbox[0].set_value(True).run()
            click(app,'Approve exact proposal locally')
            assert store.issue('ALPHA-001')['version']==1
            click(app,'Apply approved action via MCP')
            first=app.session_state['last_result']['data']
            assert not app.error and first['version']==2 and not first['replayed']
            click(app,'Apply approved action via MCP')
            assert app.session_state['last_result']['data']['replayed'] and len(store.events())==1
            click(app,'Read event history via MCP')
            assert len(app.session_state['last_result']['data']['events'])==1
            evidence={'official_sdk_stdio_client':True,'tools_discovered':10,'source_document':'retries.md',
                'duplicate_proposal_button_created_one_action':True,'approval_required_explicit_checkbox':True,
                'approval_alone_did_not_update_issue':True,'applied_status':store.issue('ALPHA-001')['status'],
                'final_issue_version':store.issue('ALPHA-001')['version'],'event_count_after_retry':len(store.events()),
                'scope':'Actual MCP subprocesses and domain state under Streamlit app runner. Only the local DB path was isolated; no fake client/tool engine. Not live-browser visual verification.'}
    (ROOT/'reports/ui-v1.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence,indent=2),flush=True)
