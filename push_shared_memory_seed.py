"""Nạp bộ nhớ tham khảo lên Worker đã triển khai. Chỉ quản trị viên chạy.

python push_shared_memory_seed.py --dry-run
python push_shared_memory_seed.py --url https://soilfirm-api.vuanh97nd.workers.dev
Thêm --publish sau khi quản trị viên kiểm tra bộ nguồn để công bố.
Mật khẩu nhập bằng getpass, không ghi vào log/file/bộ nhớ.
"""
import argparse,getpass,json,time
from pathlib import Path
from geotech_memory_sync import read_shared_seed, shared_request

def push(seed,url,credentials,publish=False,pause=2.2,post=None,sleep=time.sleep):
    items=read_shared_seed(seed)
    if credentials.get('username','').strip().lower()!='admin':
        raise ValueError('Dùng tài khoản quản trị viên để nạp bộ nguồn chung.')
    submitted=published=0;changes_cursor=0
    def request(route,body):
        sleep(pause)
        for attempt in range(3):
            try:return shared_request(url,credentials,route,body,post=post)
            except ValueError as exc:
                if 'HTTP 429' not in str(exc) or attempt==2:raise
                sleep(30)
    for start in range(0,len(items),20):
        batch=items[start:start+20]
        body={'items':[{'client_id':x['id'],'kind':x['kind'],'payload':x['payload']} for x in batch], 'cursor':changes_cursor}
        result=request('/api/memory/shared/sync',body)
        if set(result)!= {'success','ack','changes','cursor','more'} or set(result['ack'])!={x['id'] for x in batch}:
            raise ValueError('Máy chủ chưa xác nhận đúng lô bộ nhớ; dừng, có thể chạy lại.')
        changes_cursor=result['cursor'];submitted+=len(batch)
        print('Đã gửi',submitted,'/',len(items),'mảnh tham khảo; chờ công bố.',flush=True)
        if publish:
            for item in batch:
                request('/api/memory/shared/review',{'id':item['id'],'state':'approved'});published+=1
    return {'submitted':submitted,'published':published,'total':len(items)}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Nạp bộ nhớ chung SoilFirm; trial bị chặn tại API.')
    parser.add_argument('--seed',type=Path,default=Path(__file__).with_name('shared_memory_seed.json'))
    parser.add_argument('--url',default='https://soilfirm-api.vuanh97nd.workers.dev')
    parser.add_argument('--publish',action='store_true',help='Quản trị viên công bố các mảnh tham khảo đã kiểm tra.')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    try:
        if args.dry_run:print('Bộ nguồn hợp lệ:',len(read_shared_seed(args.seed)),'mảnh; không gọi máy chủ.')
        else:
            key=getpass.getpass('Khóa quản trị (không hiển thị): ')
            print(json.dumps(push(args.seed,args.url,{'username':'admin','key':key},args.publish),ensure_ascii=False))
    except (OSError,ValueError,PermissionError) as exc:
        parser.exit(1,'Chưa hoàn tất nạp bộ nhớ: '+str(exc)+'\n')
