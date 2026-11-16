"""Official SDK client launches a real stdio MCP subprocess, not in-process function calls."""
import argparse
import asyncio
import json
import sys
import os
from pathlib import Path
from mcp import Client,StdioServerParameters
from domain import ROOT


def parameters(db=None):
    env={'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'}
    selected=db if db is not None else os.environ.get('TOOLSMITH_DB')
    if selected is not None:env['TOOLSMITH_DB']=str(Path(selected).resolve())
    return StdioServerParameters(command=sys.executable,args=['-u',str(ROOT/'server.py')],env=env,cwd=str(ROOT))


def unpack(result):
    return {'is_error':bool(result.is_error),'data':result.structured_content,
        'content':[b.model_dump(mode='json',exclude_none=True) for b in result.content]}


async def call(name,arguments=None,db=None):
    async with Client(parameters(db)) as client:
        result=await asyncio.wait_for(client.call_tool(name,arguments or {}),timeout=15)
        return unpack(result)


async def inspect(db=None):
    async with Client(parameters(db)) as client:
        tools=await client.list_tools()
        resources=await client.list_resources()
        prompts=await client.list_prompts()
        return {'server':client.server_info.model_dump(mode='json') if client.server_info else None,
            'protocol_version':client.protocol_version,'tools':[t.model_dump(mode='json',exclude_none=True) for t in tools.tools],
            'resources':[r.model_dump(mode='json',exclude_none=True) for r in resources.resources],
            'prompts':[p.model_dump(mode='json',exclude_none=True) for p in prompts.prompts]}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('tool',nargs='?',default='inspect');p.add_argument('--arguments',default='{}');p.add_argument('--arguments-file');args=p.parse_args()
    raw=Path(args.arguments_file).read_text(encoding='utf-8') if args.arguments_file else args.arguments
    result=asyncio.run(inspect()) if args.tool=='inspect' else asyncio.run(call(args.tool,json.loads(raw)))
    print(json.dumps(result,indent=2,ensure_ascii=False))
