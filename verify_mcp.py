"""Actual subprocess MCP interoperability and denial/retry evidence. No LLM/provider calls."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
from pathlib import Path
import tempfile
import time
from mcp import Client
from client import parameters,unpack
from domain import ROOT,Store


async def verify(db):
    store=Store(db);trace=[];checks=[]
    def check(name,condition):
        if not condition:raise AssertionError(name)
        checks.append({'check':name,'passed':True})
    async with Client(parameters(db)) as client:
        protocol=client.protocol_version
        identity=client.server_info.model_dump(mode='json')
        tools=(await client.list_tools()).tools
        names=[t.name for t in tools]
        check('server_identity',identity['name']=='ToolSmith')
        check('ten_tools_and_no_approval_tool',len(names)==10 and not any('approve' in n or 'review' in n for n in names))
        async def call(name,args=None,error=False):
            result=await asyncio.wait_for(client.call_tool(name,args or {}),15)
            data=unpack(result)
            safe_args={k:('<REDACTED>' if k=='receipt' else v) for k,v in (args or {}).items()}
            if name=='read_document' and Path(safe_args.get('path','')).is_absolute():
                safe_args['path']='<ABSOLUTE_OUT_OF_SCOPE_TEST_PATH>'
            trace.append({'tool':name,'arguments':safe_args,'result':data})
            check(name+('_denied' if error else '_succeeded'),bool(result.is_error)==error)
            return result.structured_content
        policy=await call('get_policy')
        check('scope_alpha',policy['workspace']=='alpha')
        paths=[];cursor=None
        while True:
            page=await call('list_documents',{'limit':2,'cursor':cursor})
            paths.extend(r['path'] for r in page['documents'])
            cursor=page['next_cursor']
            if not cursor:break
        check('document_pages_complete_without_duplicates',len(paths)==6 and len(set(paths))==6)
        search=await call('search_documents',{'query':'retry','limit':5})
        check('lexical_search_returns_evidence',len(search['documents'])>0)
        source=await call('read_document',{'path':'retries.md','start_line':2,'max_lines':3})
        check('source_sha_and_line_range',source['source_sha256']==hashlib.sha256((ROOT/'fixtures/alpha/docs/retries.md').read_bytes()).hexdigest() and source['start_line']==2 and source['returned_end_line']==4)
        for path in ['../beta/secrets.md',str(ROOT/'fixtures/beta/secrets.md'),r'C:\Windows\win.ini','retries.md:stream']:
            await call('read_document',{'path':path},True)
        await call('get_issue',{'issue_id':'BETA-001'},True)
        await call('list_documents',{'limit':999},True)
        await call('list_documents',{'limit':'two'},True)
        page=await call('list_documents',{'limit':1})
        await call('list_documents',{'limit':1,'cursor':'x'+page['next_cursor'][1:]},True)
        await call('search_documents',{'query':'retry','cursor':page['next_cursor']},True)
        # Error recovery is checked on the same connected client.
        await call('list_documents',{'limit':1})
        issue_page=await call('list_issues',{'limit':1})
        issue_next=await call('list_issues',{'limit':2,'after_id':issue_page['next_after_id']})
        check('issue_keyset_pagination',len(issue_next['issues'])==2 and issue_page['issues'][0]['id']=='ALPHA-001')
        attack=await call('read_document',{'path':'adversarial-example.md'})
        check('untrusted_fixture_is_not_executed','Ignore the reviewer' in attack['text'] and store.issue('ALPHA-001')['version']==1 and not store.pending())
        resources=await client.list_resources()
        check('policy_resource_discovered',any(str(r.uri)=='toolsmith://policy' for r in resources.resources))
        resource=await client.read_resource('toolsmith://policy')
        check('resource_read_has_content',len(resource.contents)>0)
        issue_resource=await client.read_resource('toolsmith://issues/ALPHA-001')
        check('parameterized_issue_resource_read',len(issue_resource.contents)>0)
        prompt=await client.get_prompt('triage_issue',{'issue_id':'ALPHA-001'})
        check('prompt_template_received',len(prompt.messages)>0)
        request={'issue_id':'ALPHA-001','new_status':'in_progress','reason':'Inspect fictional release checklist','request_key':'verify_request_001','expected_version':1}
        await call('propose_transition',{'request':{**request,'new_status':'admin'}},True)
        await call('propose_transition',{'request':{**request,'extra_permission':True}},True)
        await call('propose_transition',{'request':{**request,'issue_id':'BETA-001'}},True)
        action=await call('propose_transition',{'request':request})
        same=await call('propose_transition',{'request':request})
        check('proposal_retry_same_id_without_domain_effect',same['action_id']==action['action_id'] and store.issue('ALPHA-001')['version']==1 and not store.events())
        await call('propose_transition',{'request':{**request,'reason':'Different payload'}},True)
        await call('apply_transition',{'action_id':action['action_id'],'receipt':'not-approved-receipt-placeholder'},True)
        approval=store.review(action['action_id'],action['payload_sha256'],True)
        check('host_approval_alone_does_not_apply',store.issue('ALPHA-001')['version']==1)
        result=await call('apply_transition',{'action_id':action['action_id'],'receipt':approval['receipt']})
        retry=await call('apply_transition',{'action_id':action['action_id'],'receipt':approval['receipt']})
        check('approved_apply_and_retry_have_one_event',result['version']==2 and retry['replayed'] and len(store.events())==1)
        await call('get_action',{'action_id':action['action_id']})
        await call('list_events')
        reject_request={**request,'issue_id':'ALPHA-002','new_status':'done','request_key':'verify_reject_002'}
        rejected=await call('propose_transition',{'request':reject_request})
        store.review(rejected['action_id'],rejected['payload_sha256'],False)
        await call('apply_transition',{'action_id':rejected['action_id'],'receipt':'rejected-receipt-placeholder'},True)
        expired=await call('propose_transition',{'request':{**reject_request,'request_key':'verify_expiry_003'}})
        expired_receipt=store.review(expired['action_id'],expired['payload_sha256'],True)['receipt']
        with store.connect() as conn:conn.execute('UPDATE actions SET expires=? WHERE id=?',(time.time()-1,expired['action_id']))
        await call('apply_transition',{'action_id':expired['action_id'],'receipt':expired_receipt},True)
        stale=await call('propose_transition',{'request':{**reject_request,'request_key':'verify_stale_004'}})
        live=await call('propose_transition',{'request':{**reject_request,'new_status':'todo','request_key':'verify_live_005'}})
        stale_receipt=store.review(stale['action_id'],stale['payload_sha256'],True)['receipt']
        live_receipt=store.review(live['action_id'],live['payload_sha256'],True)['receipt']
        await call('apply_transition',{'action_id':live['action_id'],'receipt':live_receipt})
        await call('apply_transition',{'action_id':stale['action_id'],'receipt':stale_receipt},True)
        check('stale_action_does_not_add_event',len(store.events())==2 and store.issue('ALPHA-002')['status']=='todo')
        check('no_beta_data_in_trace','BETA_ISSUE_MARKER' not in json.dumps(trace) and 'BETA_FIXTURE_MARKER' not in json.dumps(trace))
    # Reconnect after discarding the first response; the same receipt cannot cause another update.
    async with Client(parameters(db)) as client:
        replay=await client.call_tool('apply_transition',{'action_id':action['action_id'],'receipt':approval['receipt']})
        check('reconnect_retry_uses_committed_result',not replay.is_error and replay.structured_content['replayed'] and len(store.events())==2)
    return {'summary':{'checks_passed':len(checks),'checks_total':len(checks),'mcp_tools':len(names),'protocol_version':protocol,
        'actual_stdio_tool_calls':len(trace)+1,'applied_domain_events':len(store.events()),'reconnect_retry_verified':True},
        'sdk_version':importlib.metadata.version('mcp'),'server_identity':identity,'checks':checks,'trace':trace,
        'fixture_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'fixtures').rglob('*.md'))},
        'scope':'Actual official SDK client and separate stdio server subprocesses; no LLM, Claude/Codex host integration, authentication or production security certification. Expiry failure was injected in an isolated test database, not a ten-minute live wait. Approval occurred through the trusted local reviewer function outside MCP.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='reports/mcp-v1.json');args=p.parse_args()
    out=Path(args.output)
    if out.exists():raise ValueError('Choose a new report filename')
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='toolsmith-mcp-') as temp:
        report=asyncio.run(verify(Path(temp)/'isolated.db'))
    out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report['summary'],indent=2),flush=True)
