import asyncio
import json
import secrets
import streamlit as st
from client import call,inspect
from domain import Store,digest


def invoke(name,args=None):
    result=asyncio.run(call(name,args or {}))
    st.session_state['last_result']={'tool':name,**result}
    return result


def main():
    st.set_page_config(page_title='ToolSmith',layout='wide')
    st.title('ToolSmith')
    st.caption('Real MCP tools • scoped source evidence • separate local review • retry-safe issue transitions')
    st.info('Fictional alpha workspace. Every read/proposal/apply button talks to a real stdio MCP server through the official SDK client. Approval is a separate host-side action, not an MCP tool. This local demo has no authentication or LLM agent.')
    tabs=st.tabs(['Inspect MCP','Documents','Issues & proposals','Local review','Event history'])
    with tabs[0]:
        if st.button('Connect and inspect MCP'):
            try:st.session_state['inspection']=asyncio.run(inspect())
            except Exception as exc:st.error(f'MCP connection failed: {type(exc).__name__}: {exc}')
        if 'inspection' in st.session_state:
            data=st.session_state.inspection
            st.write('Negotiated protocol:',data['protocol_version'])
            st.dataframe([{'tool':t['name'],'description':t.get('description','')} for t in data['tools']],hide_index=True)
            with st.expander('Actual MCP schemas/resources/prompts'):st.json(data)
    with tabs[1]:
        query=st.text_input('Lexical search query','retry')
        if st.button('Search documents via MCP'):
            try:invoke('search_documents',{'query':query,'limit':5})
            except Exception as exc:st.error(str(exc))
        path=st.text_input('Relative document path','retries.md')
        start=st.number_input('Start line',min_value=1,value=1,step=1)
        if st.button('Read document via MCP'):
            try:invoke('read_document',{'path':path,'start_line':int(start),'max_lines':40})
            except Exception as exc:st.error(str(exc))
    with tabs[2]:
        if st.button('List issues via MCP'):
            try:invoke('list_issues',{'limit':10})
            except Exception as exc:st.error(str(exc))
        issue_id=st.selectbox('Issue',['ALPHA-001','ALPHA-002','ALPHA-003'])
        if st.button('Inspect issue via MCP'):
            try:invoke('get_issue',{'issue_id':issue_id})
            except Exception as exc:st.error(str(exc))
        status=st.selectbox('Proposed status',['in_progress','done','todo'])
        version=st.number_input('Expected issue version',min_value=1,value=1,step=1)
        reason=st.text_area('Reason','Review the fictional release checklist before continuing.',max_chars=500)
        st.caption('Inspect the current version first. Allowed transitions: todo → in_progress; in_progress → todo/done; done → in_progress.')
        if st.button('Create proposal via MCP'):
            try:
                request={'issue_id':issue_id,'new_status':status,'expected_version':int(version),'reason':reason}
                fingerprint=digest(request)
                if st.session_state.get('draft_hash')!=fingerprint:
                    st.session_state['draft_hash']=fingerprint
                    st.session_state['draft_key']='ui_'+secrets.token_hex(12)
                request['request_key']=st.session_state['draft_key']
                result=invoke('propose_transition',{'request':request})
                if not result['is_error']:
                    st.success('Proposal stored. The issue has not changed. Open Local review to inspect and confirm.')
            except Exception as exc:st.error(str(exc))
    with tabs[3]:
        st.warning('This pane is the trusted local reviewer, outside MCP. An owner with filesystem/SQLite access can bypass it; this is not a multi-user security boundary.')
        pending=Store().pending()
        if pending:
            selected=st.selectbox('Pending action',[a['action_id'] for a in pending])
            action=next(a for a in pending if a['action_id']==selected)
            st.json(action)
            agree=st.checkbox('I reviewed this exact issue, expected version, status, reason and payload hash.',key='review_'+selected+'_'+action['payload_sha256'])
            if st.button('Approve exact proposal locally',disabled=not agree):
                try:
                    approved=Store().review(selected,action['payload_sha256'],True)
                    st.session_state['approval']=approved
                    st.success('Locally approved. No issue update has been applied yet.')
                except Exception as exc:st.error(str(exc))
            if st.button('Reject proposal locally'):
                try:
                    Store().review(selected,action['payload_sha256'],False)
                    st.success('Rejected; the issue remains unchanged.')
                except Exception as exc:st.error(str(exc))
        else:st.write('No pending proposals. Create one in Issues & proposals.')
        approved=st.session_state.get('approval')
        if approved:
            st.write('Approved action:',approved['action_id'])
            st.caption('The receipt is kept in this local session and is not rendered. Applying again is an idempotent retry, not another update.')
            if st.button('Apply approved action via MCP'):
                try:invoke('apply_transition',{'action_id':approved['action_id'],'receipt':approved['receipt']})
                except Exception as exc:st.error(str(exc))
    with tabs[4]:
        if st.button('Read event history via MCP'):
            try:invoke('list_events')
            except Exception as exc:st.error(str(exc))
    if 'last_result' in st.session_state:
        result=st.session_state.last_result
        st.subheader('Actual MCP result: '+result['tool'])
        if result['is_error']:st.error('Tool rejected this request. No success is inferred from an error response.')
        st.json(result)
    st.caption('Search is lexical. The server provides tools/resources/prompts but does not run an LLM or claim prompt-injection immunity.')


if __name__=='__main__':main()
