import argparse,json
from . import SoilFirmAgent,ToolSet,make_provider
p=argparse.ArgumentParser();p.add_argument('--provider',default='qwen3:8b');p.add_argument('--model');p.add_argument('--project',default='./project');p.add_argument('--json-tools',action='store_true');p.add_argument('question');args=p.parse_args()
agent=SoilFirmAgent(make_provider(args.provider,model=args.model,native_tools=not args.json_tools),ToolSet(args.project,progress=lambda x:print(x,flush=True)))
print(json.dumps(agent.run(args.question),ensure_ascii=False,indent=2))
