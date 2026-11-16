"""Explicit host-side reviewer. Never registered as an MCP tool."""
import argparse
import json
from domain import Store


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['init','pending','approve','reject'])
    p.add_argument('--action-id')
    p.add_argument('--payload-hash')
    args=p.parse_args();store=Store()
    if args.action=='init':print('Local fictional workspace initialized; existing issue state preserved.')
    elif args.action=='pending':print(json.dumps(store.pending(),indent=2))
    else:
        if not args.action_id or not args.payload_hash:p.error('Review requires --action-id and the exact displayed --payload-hash')
        print(json.dumps(store.review(args.action_id,args.payload_hash,args.action=='approve'),indent=2))
