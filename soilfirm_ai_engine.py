"""Allowlisted AI tools backed by SOILFIRM PRO calculation modules; no generated code execution."""
from copy import deepcopy
from dataclasses import asdict
import inspect
import json
import math
from pathlib import Path


def knowledge_context(question):
    import model, treatment_optimizer, weak_soil
    refs={'TCCS 41:2022/TCĐBVN':'Nhận dạng đất yếu và thiết kế đường trên nền đất yếu',
          'TCVN 9355:2013':'Tính cố kết, thoát nước và sức cản bấc thấm',
          '22 TCN 262':'Giới hạn kiểm toán đang được giao diện tham chiếu',
          'CDM TCVN/BS và ALiCC':'Dùng mô đun CDM/ALiCC và thông số đã khai báo'}
    q=question.lower();functions=[]
    if any(x in q for x in ('đất yếu','tccs','chỉ tiêu')):functions.append(weak_soil.weak_criteria)
    if any(x in q for x in ('pvd','bấc','9355','hansbo','thoát nước')):functions.extend([model.get_hansbo_f,model.degree_vertical])
    if any(x in q for x in ('lún','cố kết','công thức')):functions.append(model.settlement)
    if 'tối ưu' in q:functions.append(treatment_optimizer.optimize_drainage_time)
    excerpts=[]
    for fn in functions:
        try:excerpts.append(fn.__module__+'.'+fn.__name__+':\n'+inspect.getsource(fn)[:3500])
        except (OSError,TypeError):excerpts.append(fn.__module__+'.'+fn.__name__+': '+str(fn.__doc__ or ''))
    return json.dumps({'references_in_software':refs,'implementation_excerpts':excerpts,
        'optimization_workflow':optimization_instructions(),
        'scope':'Các trích đoạn là cách SOILFIRM PRO triển khai, không phải nguyên văn tiêu chuẩn. Chưa có toàn văn tiêu chuẩn: không suy đoán số điều, bảng hoặc khẳng định hiệu lực. Dùng file tiêu chuẩn người dùng gửi khi cần viện dẫn cụ thể.'},ensure_ascii=False)[:10000]


def optimization_instructions():
    return {
        'inputs':'Đồng bộ số liệu giao diện và phạm vi nền đường/nền mở rộng trước khi lấy bản sao tính. Không tự bịa số liệu địa chất, vật liệu, đơn giá.',
        'CDM':'Tính cấu hình đã nhập, sau đó quét Lc, s và số lớp gia cường bằng bộ tính CDM. Loại cấu hình không đạt lún, cường độ cọc, ứng suất đất hoặc lực kéo gia cường. Chọn theo chỉ số vật liệu của bộ tối ưu; chỉ số này không phải giá tiền.',
        'ALiCC':'Es = 250 × Co của lớp đất được chọn. Kiểm tra ΔS = |Ssoil − Scol| ≤ [ΔS] do người dùng khai báo; thiếu giới hạn thì không kết luận đạt đầy đủ. Quét Lc, s; nếu có vải/lưới thì quét số lớp, nếu có đệm gia cố thì quét chiều dày đệm. Kiểm tra S tổng, Pcol×Fs≤qu, lực kéo gia cường, cắt thủng/uốn đệm. Giữ phạm vi địa chất đã khảo sát.',
        'PVD_SD':'Dùng khoảng cách/đường kính đã khai báo; chiều sâu xử lý tới đáy lớp đất yếu theo bộ tính. Nếu có dải khoảng cách do người dùng nhập thì tính từng khoảng cách. Tìm thời gian sớm nhất đồng thời Sc dư≤giới hạn và U>90%. Với giới hạn ngày chờ, loại cấu hình vượt giới hạn; chọn ít điểm thoát nước hoặc ít ngày chờ theo tiêu chí.',
        'gia_tai':'Dùng chiều cao gia tải đã khai báo; bộ tối ưu hiện có điều chỉnh theo Hgh khi có dữ liệu cường độ. Tính thời gian chờ, kiểm tra điều kiện lún/U và báo H gia tải, Hgh, thời gian cùng thông số thoát nước.',
        'cho_lun':'Không thêm PVD/SD. Tìm thời gian sớm nhất đạt lún dư và U; báo rõ nếu vượt giới hạn ngày chờ.',
        'output':'Luôn trả kết quả thực từ bộ tính: đầu vào, thông số phương án, điều kiện kiểm toán, số cấu hình đã thử, chi tiết theo lớp và vị trí và nguyên nhân không đạt. Không kết luận ổn định mái dốc từ riêng điều kiện lún.'}


def _grid(low,high,step,label):
    if any(not math.isfinite(v) for v in (low,high,step)) or low<=0 or high<low or step<=0:
        raise ValueError('Phạm vi tối ưu '+label+' chưa hợp lệ.')
    count=int((high-low)/step+1e-8)+1
    if count>250:raise ValueError('Quá nhiều bước tối ưu '+label+'; tăng bước quét.')
    return [round(low+i*step,8) for i in range(count)]


def optimize_cdm(project,name,settings,progress=None):
    from batch_calculation import _cdm_standard,_cdm_alicc
    from model import cdm_design_project
    scope=settings.get('cdm_scope') or ('Nền mở rộng' if project.expansion_width>0 else 'Nền đường')
    if scope not in ('Nền đường','Nền mở rộng'):raise ValueError('Phạm vi CDM không hợp lệ.')
    standard=name=='CDM (TCVN/BS)'
    calculate=_cdm_standard if standard else _cdm_alicc
    initial=calculate(deepcopy(project),scope)
    design=cdm_design_project(project,scope)
    depth=sum(s.thickness for s in design.soils)
    params=initial['details']['params']
    d=params['D']
    lc_min=float(settings.get('cdm_lc_min',min(3.0 if standard else 5.0,depth)))
    lc_max=min(depth,float(settings.get('cdm_lc_max',min(20.0 if standard else 22.0,depth))))
    lc_step=float(settings.get('cdm_length_step',.5))
    s_min=float(settings.get('cdm_s_min',max(1.1,d+.1) if standard else d+.3))
    default_s_max=2.5 if standard else min(params['H']-.05,2.5)
    s_max=float(settings.get('cdm_s_max',max(s_min,default_s_max)))
    s_step=float(settings.get('cdm_s_step',.1))
    _grid(lc_min,lc_max,lc_step,'Lc');_grid(s_min,s_max,s_step,'s')
    state_attr='cdm_inputs' if standard else 'alicc_inputs'
    def inputs(trial):
        states=getattr(trial,state_attr)
        saved=states if ('cdm' if standard else 'D') in states else states[scope]
        return saved, saved['cdm'] if standard else saved
    if standard:
        from cdm import optimize_cdm_dimensions
        det=initial['details'];saved,_=inputs(project)
        if progress:progress('CDM TCVN/BS: đang quét chiều dài, khoảng cách và lớp gia cường…')
        optimum=optimize_cdm_dimensions(design,params,det['stress_params'],det['subgrade_params'],det['geo_params'],bool(saved.get('use_geo')),
            s_range=(s_min,s_max,s_step),lc_range=(lc_min,lc_max,lc_step),
            n_layer_range=(1,int(settings.get('cdm_n_layer_max',4))),settlement_limit_cm=project.residual_limit_cm)
        trial=deepcopy(project);state,values=inputs(trial)
        if optimum:
            values['Lc']=optimum['Lc'];values['s']=optimum['s']
            state.setdefault('geo',{})['n_layer']=optimum['n_layer']
            final=calculate(trial,scope)
            # The module applies a stricter residual tolerance for end-bearing piles.
            if 'Cọc chống' in params.get('pile_type',''):
                from cdm import END_BEARING_RESIDUAL_TOL_CM
                final['details']['limit']=END_BEARING_RESIDUAL_TOL_CM
            final['details']['optimization_index']=optimum['cost_index']
        else:final=initial
        final['details']['optimization_found']=bool(optimum)
    else:
        from alicc import REINFORCEMENT_FABRIC,REINFORCEMENT_GRID,REINFORCEMENT_SURFACE
        saved,_=inputs(project);kind=saved.get('kind','Không dùng')
        lengths=_grid(lc_min,lc_max,lc_step,'Lc');spacings=_grid(s_min,s_max,s_step,'s')
        best=None;best_index=float('inf');attempts=0;errors=[]
        for spacing in spacings:
            if progress:progress('ALiCC: đang quét s=%.2f m, Lc và gia cường…'%spacing)
            for length in lengths:
                layers=range(1,int(settings.get('cdm_n_layer_max',5))+1) if kind in (REINFORCEMENT_FABRIC,REINFORCEMENT_GRID) else (int(float(str(saved.get('n_layer',1)).replace(',','.'))),)
                covers=(.3,.4,.5,.6,.7,.8,.9,1.0) if kind==REINFORCEMENT_SURFACE else (None,)
                for n_layer in layers:
                    for cover in covers:
                        trial=deepcopy(project);state,values=inputs(trial)
                        values.update(Lc=length,s=spacing,n_layer=n_layer)
                        if params['pattern']=='Lưới chữ nhật':values['s_short']=max(d+.1,spacing-.2)
                        if cover is not None:values['surface_h']=cover
                        attempts+=1
                        try:candidate=calculate(trial,scope)
                        except Exception as exc:
                            if str(exc) not in errors:errors.append(str(exc))
                            continue
                        if not candidate['pass_check']:continue
                        index=candidate['details']['result']['ap']*length
                        if kind in (REINFORCEMENT_FABRIC,REINFORCEMENT_GRID):index+=.08*n_layer
                        elif cover is not None:index+=.5*cover
                        if index<best_index:best,best_index=candidate,index
        final=best or initial
        final['details'].update(optimization_found=best is not None,optimization_index=best_index if best else None,
            configuration_count=attempts,optimization_errors=errors[:3])
    final['details']['search_ranges']={'Lc (m)':(lc_min,lc_max,lc_step),'s (m)':(s_min,s_max,s_step)}
    final['details']['optimization_note']='Chỉ số vật liệu của bộ tối ưu; chưa quy đổi giá tiền.'
    if not final['details']['optimization_found']:
        final['details']['optimization_note']='Không tìm được cấu hình đạt trong dải quét; hiển thị kiểm toán cấu hình đã nhập.'
    return final


def optimize_drains(project,name,settings,criterion,progress=None):
    from batch_calculation import run_option
    prefix='pvd' if name.startswith('PVD') else 'sd' if name.startswith('SD') else None
    candidates=[None]
    if prefix:
        spacing=settings.get(prefix+'_spacing');diameter=settings.get(prefix+'_diameter')
        if any(v is None or not math.isfinite(float(v)) or float(v)<=0 for v in (spacing,diameter)):
            raise ValueError('Cần khoảng cách và đường kính '+prefix.upper()+' dương đã khai báo.')
        low=settings.get(prefix+'_spacing_min',spacing);high=settings.get(prefix+'_spacing_max',spacing)
        candidates=_grid(float(low),float(high),float(settings.get(prefix+'_spacing_step',.1)),prefix.upper())
    heights=[settings.get('surcharge_height',0.0) if 'gia tải' in name else 0.0]
    if 'gia tải' in name:
        from treatment_optimizer import limiting_fill_height
        hgh=limiting_fill_height(project)
        fill=(project.expansion_h_design if project.expansion_width>0 and project.expansion_h_design>0 else project.h_design)+project.h_kcad+project.h_bl
        cap=max(0.0,hgh-fill) if hgh is not None else None
        if cap is not None:
            if cap<=0:raise ValueError('Không còn chiều cao gia tải dương trong giới hạn Hgh của bộ tính; kiểm tra dữ liệu cường độ và chiều cao nền.')
            high=min(cap,float(settings.get('surcharge_height_max',cap)))
            low=min(high,float(settings.get('surcharge_height_min',min(.5,high))))
            heights=_grid(low,high,float(settings.get('surcharge_height_step',.5)),'gia tải')
            if high not in heights:heights.append(high)
        elif not heights[0] or heights[0]<=0:
            raise ValueError('Chưa có chiều cao gia tải hoặc chỉ tiêu cường độ để tính Hgh; cần bổ sung dữ liệu.')
    evaluated=[];max_wait=settings.get('max_wait_days')
    for spacing in candidates:
        for height in heights:
            trial_settings=dict(settings);trial_settings['surcharge_height']=height
            if prefix:trial_settings[prefix+'_spacing']=spacing
            if progress:progress('%s: s=%s m; gia tải %.2f m…'%(name,spacing if spacing is not None else '—',height if 'gia tải' in name else 0.0))
            candidate_project=deepcopy(project)
            if prefix and settings.get(prefix+'_pattern'):candidate_project.drain_pattern=settings[prefix+'_pattern']
            result=run_option(candidate_project,name,trial_settings)
            wait=result['details'].get('wait_days')
            if max_wait is not None and (wait is None or wait>max_wait):
                result['pass_check']=False;result['details']['reason']='Vượt giới hạn ngày chờ đã khai báo.'
            result['details']['max_wait_days']=max_wait
            evaluated.append(result)
    valid=[r for r in evaluated if r['pass_check']]
    if valid:
        if criterion=='wait':best=min(valid,key=lambda r:r['details'].get('wait_days',float('inf')))
        elif prefix:best=min(valid,key=lambda r:(-r['project'].drain_spacing,r['project'].surcharge_height,r['details'].get('wait_days',float('inf'))))
        else:best=min(valid,key=lambda r:(r['project'].surcharge_height,r['details'].get('wait_days',float('inf'))))
    else:best=min(evaluated,key=lambda r:r['residual_cm'])
    best['details']['configuration_count']=len(evaluated)
    best['details']['optimization_note']='Tìm thời gian sớm nhất đạt Sc dư và U; xét khoảng cách đã khai báo.'
    return best


def _valid_project(p):
    from ai_analysis_data import validate_analysis_project
    if not p.soils:raise ValueError('Chưa có địa chất.')
    validate_analysis_project(p)
    if not math.isfinite(p.residual_limit_cm) or p.residual_limit_cm<=0:raise ValueError('Giới hạn lún dư phải lớn hơn 0.')


def _record(p,name,result,length):
    from treatment_boq import calculate_section_boq
    rec={'opt_name':name,'payload':result['payload'],'project_snapshot':result['project'],
         'residual':result['residual_cm'],'status':'ĐẠT' if result['pass_check'] else 'CHƯA ĐẠT'}
    if length is not None and length>0:rec['boq']=calculate_section_boq(rec,length,result['project'])
    else:rec['boq_missing']='Chưa có chiều dài phân đoạn: chưa tính tổng khối lượng.'
    return rec


def before_treatment(project):
    """Use the same untreated consolidation calculation as the before-treatment tab."""
    from model import axes, consolidation
    _valid_project(project)
    p=deepcopy(project)
    p.replacement_depth=p.bamboo_depth=p.cajuput_depth=0.0
    p.treatment_group='drainage';p.treatment='Chờ lún'
    p.mechanical_wait=p.mechanical_surcharge=False
    p.surcharge_height=p.vacuum_pressure=0.0
    day=p.assessment_days
    if not math.isfinite(day) or day<0:raise ValueError('Thời gian đánh giá trước xử lý phải không âm.')
    locations=[]
    for index,(name,_) in enumerate(axes(p)):
        layers,row=consolidation(p,day,radial=False,axis_index=index,treated=False)
        row['phân_tố']=layers
        locations.append(row)
    relevant=[r for r in locations if p.expansion_width<=0 or 'nền mở rộng' in r['vị_trí'].lower()]
    if not relevant:raise ValueError('Không có vị trí tính toán trong phạm vi xử lý.')
    residual=max(r['Sc_dư_cm'] for r in relevant)
    return {'locations':locations,'evaluation_day':day,'residual_cm':residual,
            'limit_cm':p.residual_limit_cm,'pass_check':residual<=p.residual_limit_cm,
            'scope':'Nền mở rộng' if p.expansion_width>0 else 'Nền đường'}


def calculation_checks(name,result,limit):
    """Expose the checks already used by each module, without new design formulas."""
    rows=[]
    def add(label,value,allowed,unit='',strict=False):
        valid=math.isfinite(float(value)) and math.isfinite(float(allowed))
        passed=valid and (value>allowed if strict else value<=allowed)
        rows.append({'option':name,'check':label,'value':value,'limit':allowed,
                     'unit':unit,'operator':'>' if strict else '≤','passed':passed})
    details=result['details'];r=details.get('result',{})
    add('S tổng' if name=='CDM (ALiCC)' else 'Sc dư',result['residual_cm'],limit,'cm')
    if 'u_pct' in details:add('U',details['u_pct'],90.0,'%',True)
    if details.get('max_wait_days') is not None:
        add('Ngày chờ',details.get('wait_days',float('inf')),details['max_wait_days'],'ngày')
    if name=='CDM (TCVN/BS)':
        st=r['stress']
        for key,label,allowed in [('qu_tt1','qu,TT1',st['qu_allow']),('sigma_p','σp',st['qu_allow']),('sigma_s','σs',st['Rtc'])]:
            add(label,st[key],allowed,'T/m²')
        if r.get('geo'):add('Tr',r['geo']['Tr'],r['geo']['Td_fn'],'T/m')
    elif name=='CDM (ALiCC)':
        add('Pcol × Fs',r['Pcol']*details['params']['Fs'],details['params']['qu'],'T/m²')
        if r.get('differential_checked'):
            add('ΔS = |Ssoil − Scol|',r['differential_cm'],r['differential_limit_cm'],'cm')
        else:
            rows.append({'option':name,'check':'ΔS = |Ssoil − Scol|','value':r.get('differential_cm'),
                         'limit':None,'unit':'cm','operator':'≤','passed':False,'checked':False})
        rein=r.get('reinforcement')
        if rein:
            add('Tr',rein['Tr'],rein['Td_fn'],'T/m')
        cover=r.get('surface')
        if cover:
            add('Cắt thủng τ',cover['shear'],cover['shear_allow'],'T/m²')
            add('Uốn σ',cover['sigma_k'],cover['bending_allow'],'T/m²')
    return rows


def design_parameters(name,result):
    p=result['project'];payload=result['payload'];details=result['details'];params=details.get('params',{})
    values={}
    def put(key,label,value,unit):
        values[key]={'label':label,'value':value,'unit':unit}
    if name.startswith(('Đào','Cọc tre','Cừ tràm')):
        put('excavation','Chiều sâu đào thay đất',p.replacement_depth,'m')
        put('bamboo','Chiều dài cọc tre',p.bamboo_depth,'m')
        put('cajuput','Chiều dài cừ tràm',p.cajuput_depth,'m')
        put('treatment_depth','Chiều sâu xử lý',p.replacement_depth+max(p.bamboo_depth,p.cajuput_depth),'m')
    elif name.startswith('CDM'):
        for key,label,source in [('cdm_d','Đường kính cọc CDM','D'),('cdm_s','Khoảng cách cọc CDM','s'),('cdm_lc','Chiều dài cọc CDM','Lc')]:
            put(key,label,params.get(source,payload.get(key)),'m')
        if 's_short' in params:put('s_short','Khoảng cách cạnh ngắn',params['s_short'],'m')
        put('pattern','Sơ đồ bố trí',params.get('pattern'),'')
        put('pile_type','Loại cọc',params.get('pile_type'),'')
        put('scope','Phạm vi CDM',details.get('scope'),'')
        put('cdm_n_layer','Số lớp vải/lưới',payload.get('cdm_n_layer',0),'lớp')
        if name=='CDM (ALiCC)':
            r=details['result']
            for key,label,unit in [('Es_used','Es = 250 × Co','T/m²'),('Co_used','Co của lớp đất chọn','T/m²'),
                ('es_layer_name','Lớp đất tính Es',''),('es_layer_no','Số thứ tự lớp đất',''),
                ('Ssoil_cm','Lún đất giữa cọc','cm'),('Scol_cm','Lún cọc','cm'),
                ('differential_cm','Chênh lún ΔS = |Ssoil − Scol|','cm'),('differential_limit_cm','Giới hạn chênh lún [ΔS]','cm')]:
                put(key,label,r.get(key),unit)
        if details.get('surface_params',{}).get('enabled'):put('surface_h','Chiều dày đệm gia cố',details['surface_params']['thickness'],'m')
    else:
        if name.startswith(('PVD','SD')):
            put('drain_spacing','Khoảng cách thoát nước',p.drain_spacing,'m')
            put('drain_diameter','Đường kính tương đương thoát nước',p.drain_diameter,'cm')
            put('drain_length','Chiều sâu PVD/SD',payload.get('drain_length',p.drain_length),'m')
            put('pattern','Sơ đồ bố trí',p.drain_pattern,'')
        put('surcharge_height','Chiều cao gia tải',payload.get('surcharge_height',0),'m')
        put('wait_days','Thời gian chờ',details.get('wait_days'),'ngày')
        put('evaluation_day','Thời điểm đánh giá sau thi công',details.get('day'),'ngày')
        if details.get('hgh') is not None:put('hgh','Chiều cao đắp giới hạn Hgh',details['hgh'],'m')
    if details.get('configuration_count') is not None:put('configurations','Số cấu hình đã tính',details['configuration_count'],'cấu hình')
    for label,bounds in details.get('search_ranges',{}).items():
        put('range_'+label,'Dải quét '+label,'%g → %g; bước %g'%bounds,'')
    if details.get('optimization_note'):put('optimization','Quy trình lựa chọn',details['optimization_note'],'')
    if details.get('reason'):put('reason','Nguyên nhân không đạt',details['reason'],'')
    return values


def complete_calculation_output(name,result):
    """Keep all native output fields; supplement drainage/mechanical results by axis."""
    details=result['details']
    if name.startswith('CDM'):return
    from model import axes,consolidation,treatment_history,stage_schedule
    p=result['project'];day=details.get('day',0.0)
    outputs=[]
    for index,(axis,_) in enumerate(axes(p)):
        if p.treatment_group=='mechanical':
            layers,metrics=consolidation(p,0.0,axis_index=index,treated=True)
            outputs.append({'vị_trí':axis,'kết_quả':metrics,'phân_tố':layers})
        else:
            history,layers=treatment_history(p,day,max(1.0,day/30.0),p.treatment,index)
            outputs.append({'vị_trí':axis,'kết_quả':history[-1],'phân_tố':layers,'diễn_biến_lún':history})
    details['output_locations']=outputs
    details['stage_schedule']=stage_schedule(p)


def missing_calculation_inputs(project,names,settings):
    """Collect declared numeric inputs; never invent design values or relax checks."""
    from alicc import es_layer_index
    from model import sync_data_settlement_limits
    sync_data_settlement_limits(project)
    requirements=[]
    scope=settings.get('cdm_scope') or ('Nền mở rộng' if project.expansion_width>0 else 'Nền đường')
    def require(value,target,key,option,group=None,positive=False,soil_index=None):
        try:
            number=float(str(value).replace(',','.'))
            valid=math.isfinite(number) and (not positive or number>0)
        except (TypeError,ValueError):valid=False
        if valid:return
        label,unit=OUTPUT_LABELS.get(key,(key,''))
        if key=='differential_limit_cm':label,unit='Chênh lún cho phép [ΔS]','cm'
        if key=='co':label,unit='Co lớp đất '+str(soil_index+1),'T/m²'
        identity=(target,scope,group,key,soil_index)
        if any(tuple(r['identity'])==identity for r in requirements):return
        requirements.append({'identity':identity,'target':target,'scope':scope,'group':group,'key':key,
            'label':label,'unit':unit,'option':option,'positive':positive,'soil_index':soil_index,
            'value':'' if value is None else str(value)})
    for name in names:
        if not name.startswith('CDM'):
            prefix='pvd' if name.startswith('PVD') else 'sd' if name.startswith('SD') else None
            if prefix:
                for suffix in ('spacing','diameter'):
                    key=prefix+'_'+suffix
                    require(settings.get(key),'treatment',key,name,positive=True)
            if 'gia tải' in name:
                from treatment_optimizer import limiting_fill_height
                if limiting_fill_height(project) is None:
                    require(settings.get('surcharge_height'),'treatment','surcharge_height',name,positive=True)
            continue
        standard=name=='CDM (TCVN/BS)';target='cdm_inputs' if standard else 'alicc_inputs'
        states=getattr(project,target,{}) or {}
        saved=states if ('cdm' if standard else 'D') in states else states.get(scope,{})
        if standard:
            groups={'cdm':['D','s','Lc','qu_val','Ec'],'stress':['n','Fs','qH','f_fs','f_q'],'subgrade':['m']}
            if saved.get('subgrade',{}).get('rtc_method')=='Nhập c, φ cắt nhanh':groups['subgrade']+=['c_manual','phi_manual']
            if saved.get('use_geo'):
                groups['geo']=['eps','phi_dap','n_layer','fm11','fm12','fm21','fm22','fn']
                groups['geo']+=['T_char_kn'] if saved.get('reinforcement')=='Lưới địa kỹ thuật' else ['Tmax','eps_max']
            for group,keys in groups.items():
                for key in keys:require(saved.get(group,{}).get(key),target,key,name,group,positive=key in ('D','s','Lc','Ec','qu_val','Fs','m','n_layer'))
        else:
            keys=['D','s','Lc','Ec','qu','Fs','theta','settlement_limit','qH','differential_limit_cm']
            if saved.get('pattern')=='Lưới chữ nhật':keys+=['s_short']
            from alicc import REINFORCEMENT_FABRIC,REINFORCEMENT_GRID,REINFORCEMENT_SURFACE
            kind=saved.get('kind')
            if kind in (REINFORCEMENT_FABRIC,REINFORCEMENT_GRID):
                keys+=['eps','phi_dap','n_layer','fm11','fm12','fm21','fm22','fn','f_fs','f_q']
                keys+=['T_char_kn'] if kind==REINFORCEMENT_GRID else ['Tmax','eps_max']
            if kind==REINFORCEMENT_SURFACE:keys+=['surface_h','q_allow','shear_strength','su_soil','qu_surface','alpha','bend_ratio','Esa','spt_n']
            for key in keys:require(saved.get(key),'alicc_inputs',key,name,positive=key in ('D','s','Lc','Ec','qu','Fs','settlement_limit','differential_limit_cm','s_short','n_layer'))
            try:index=es_layer_index(saved.get('es_layer_idx','0'))
            except ValueError:index=-1
            if 0<=index<len(project.soils):require(project.soils[index].co,'soil','co',name,positive=True,soil_index=index)
    return requirements


def apply_calculation_inputs(project,requirements,values):
    """Validate every entry before committing any user-entered input."""
    parsed=[]
    for requirement,value in zip(requirements,values):
        number=float(str(value).strip().replace(',','.'))
        if not math.isfinite(number) or (requirement['positive'] and number<=0):
            raise ValueError(requirement['label']+' phải '+('lớn hơn 0.' if requirement['positive'] else 'là số hữu hạn.'))
        parsed.append((requirement,str(number)))
    if len(values)!=len(requirements):raise ValueError('Cần nhập đầy đủ thông số còn thiếu.')
    for r,value in parsed:
        if r['target'] in ('treatment','app_var'):continue
        if r['target']=='soil':setattr(project.soils[r['soil_index']],r['key'],float(value));continue
        states=getattr(project,r['target'],{}) or {}
        legacy=('cdm' if r['target']=='cdm_inputs' else 'D') in states
        if legacy:states={'Nền đường':states}
        saved=states.setdefault(r['scope'],{})
        destination=saved.setdefault(r['group'],{}) if r['group'] else saved
        destination[r['key']]=value
        setattr(project,r['target'],states)
    return parsed


def execute_tool(plan,p,settings,length=None,source=None,output=None,scope='all',progress=None):
    from batch_calculation import OPTIONS,run_option,natural_metrics,run_batch
    from model import assess_locations,stage_schedule
    _valid_project(p)
    tool=plan.get('tool');params=plan.get('params',{})
    if not isinstance(params,dict):raise ValueError('Tham số công cụ AI chưa hợp lệ.')
    if tool=='calculate':
        if progress:progress('Đang tính trước xử lý tại các vị trí tính toán…')
        before=before_treatment(p)
        return {'summary':{'tool':tool,'before':before,'residual_limit_cm':p.residual_limit_cm,
                           'limit_source':p.residual_limit_source}}
    if tool=='batch':
        if not source or not Path(source).is_file():raise ValueError('Import file Data Excel hoặc gửi file XLSX trước khi tính hàng loạt.')
        no_export = bool(settings.get('no_export', False))
        if not no_export and not output:raise ValueError('Chọn thư mục xuất kết quả AI trước khi tính hàng loạt.')
        numbers=params.get('numbers',[])
        if not isinstance(numbers,list) or not numbers or len(numbers)>100 or any(type(n) is not int or n<=0 for n in numbers) or len(numbers)!=len(set(numbers)):raise ValueError('Cần danh sách STT hợp lệ, tối đa 100 phân đoạn/lần.')
        priorities=params.get('priorities',[])
        if not isinstance(priorities,list) or len(priorities)>5 or any(n not in OPTIONS for n in priorities):raise ValueError('Chọn tối đa 5 phương án hợp lệ để tính hàng loạt.')
        batch_settings=deepcopy(settings)
        batch_settings.update(ai_optimize=True,export_individual=not no_export)
        notify=(lambda count,total,number,message:progress(f'AI · đoạn {count}/{total} · STT {number}: {message}')) if progress else None
        folder,records,failures=run_batch(source,numbers,priorities,p,output,batch_settings,progress=notify)
        if progress:progress('Đã tính xong. Đang tổng hợp bảng kết quả…' if no_export else 'Đã xuất PDF/JSON. Đang tổng hợp bảng kết quả…')
        return {'summary':{'tool':tool,'output_folder':folder,'criterion':'Phương án đạt đầu tiên theo thứ tự ưu tiên đã khai báo',
            'records':[{'section_no':r['section_no'],'option':r['opt_name'],'status':r['status'],'residual_cm':r['residual'],'boq':r.get('boq')} for r in records], 'failures':failures},'records':records}
    if tool not in ('optimize','boq'):raise ValueError('Công cụ AI không được hỗ trợ.')
    names=params.get('options',list(OPTIONS))
    if not isinstance(names,list) or not names or len(names)>11 or len(set(names))!=len(names) or any(n not in OPTIONS for n in names):raise ValueError('Tên phương án chưa hợp lệ.')
    if scope=='mechanical':names=[n for n in names if n in OPTIONS[:3]]
    elif scope=='drainage':names=[n for n in names if n in OPTIONS[5:]]
    elif scope=='cdm':names=[n for n in names if n in OPTIONS[3:5]]
    if not names:raise ValueError('Chọn ít nhất một phương án thuộc phạm vi cần tính.')
    requirements=missing_calculation_inputs(p,names,settings)
    if requirements:
        return {'summary':{'tool':tool,'attempts':[],'missing':[],
            'recommendation':'Cần bổ sung thông số trước khi tính và so sánh.'},
            'input_requirements':requirements,'requested_plan':deepcopy(plan)}
    criterion=params.get('criterion','priority')
    if criterion not in ('priority','wait'):raise ValueError('Tiêu chí lựa chọn chưa hợp lệ.')
    if progress:progress('Đang tính trước xử lý để làm mốc so sánh…')
    before=before_treatment(p)
    attempts=[];selected=None;options={};checks=[];candidates=[]
    for index,name in enumerate(names,1):
        if progress:progress('Đang tính phương án %d/%d: %s'%(index,len(names),name))
        try:
            if name.startswith('CDM'):result=optimize_cdm(deepcopy(p),name,settings,progress)
            elif name.startswith(('PVD','SD','Chờ lún')):result=optimize_drains(deepcopy(p),name,settings,criterion,progress)
            else:result=run_option(deepcopy(p),name,settings)
            if not math.isfinite(float(result['residual_cm'])):
                raise ValueError(result['details'].get('reason') or 'Bộ tính không tìm được kết quả hữu hạn đạt yêu cầu.')
            limit=result['details'].get('limit',p.residual_limit_cm)
            option_checks=calculation_checks(name,result,limit)
            result['pass_check']=bool(result['pass_check']) and all(c['passed'] for c in option_checks)
            complete_calculation_output(name,result)
            rec={'opt_name':name,'payload':result['payload'],'project_snapshot':result['project'],
                 'residual':result['residual_cm'],'status':'ĐẠT' if result['pass_check'] else 'CHƯA ĐẠT'}
            if not name.startswith(('PVD','SD','Chờ lún')):result['details'].setdefault('wait_days',0.0)
            if result['payload']:options[name]=rec
            checks.extend(option_checks)
            attempts.append({'option':name,'pass_check':result['pass_check'],'residual_cm':result['residual_cm'],'limit_cm':limit,'payload':result['payload'],'calculation':result['details'],'design':design_parameters(name,result),'boq':rec.get('boq'),'boq_missing':rec.get('boq_missing')})
            if result['pass_check']:
                wait=result['details'].get('wait_days')
                if wait is None and not name.startswith(('PVD','SD','Chờ lún')):wait=0.0
                candidates.append((rec,wait))
        except Exception as exc:attempts.append({'option':name,'error':str(exc)})
    if candidates:
        if criterion=='wait':
            known=[c for c in candidates if c[1] is not None and math.isfinite(c[1])]
            if known:selected=min(known,key=lambda c:c[1])[0]
        else:selected=candidates[0][0]
    if before['pass_check']:
        recommendation='Trước xử lý đạt điều kiện lún dư; xem xét giữ nguyên theo thời điểm đánh giá đã nhập.'
    else:recommendation='Đề xuất: '+(selected['opt_name'] if selected else 'Chưa có phương án đủ điều kiện theo tiêu chí đã chọn')+'.'
    summary={'tool':tool,'before':before,'checks':checks,'recommendation':recommendation,
             'limit_source':p.residual_limit_source,
             'criterion':'Ít ngày chờ nhất trong các phương án đạt; khi bằng nhau dùng thứ tự ưu tiên' if criterion=='wait' else 'Phương án đạt đầu tiên theo thứ tự ưu tiên đã chọn',
             'attempts':attempts,'selected_option':selected['opt_name'] if selected else None,
             'missing':[]}
    return {'summary':summary,'selected':selected,'options':options,'requested_plan':deepcopy(plan)}


OUTPUT_LABELS={
    'result':('Kết quả mô đun',''),'params':('Thông số phương án',''),'stress':('Ứng suất',''),
    'stress_params':('Thông số tải trọng',''),'subgrade_params':('Thông số đất nền',''),
    'geo_params':('Thông số gia cường',''),'geo':('Kết quả gia cường',''),'reinforcement':('Kết quả gia cường',''),
    'surface':('Kết quả đệm gia cố',''),'surface_params':('Thông số đệm gia cố',''),
    'output_locations':('Kết quả tại các vị trí',''),'positions':('Kết quả tại các vị trí',''),
    'phân_tố':('Phân tố / lớp đất',''),'rows_lun':('Các thành phần lún',''),'settlement_rows':('Lún dưới mũi cọc',''),
    'stage_schedule':('Tiến độ thi công',''),'diễn_biến_lún':('Diễn biến lún theo thời gian',''),
    'configuration_count':('Số cấu hình đã tính','cấu hình'),'search_ranges':('Dải tìm kiếm',''),
    'optimization_note':('Quy trình tối ưu',''),'optimization_found':('Tìm được cấu hình tối ưu đạt',''),
    'optimization_index':('Chỉ số vật liệu lựa chọn',''),'optimization_errors':('Lỗi trong quá trình quét',''),
    'reason':('Nguyên nhân không đạt',''),'warnings':('Thông tin cần lưu ý',''),
    'D':('Đường kính cọc D','m'),'s':('Khoảng cách cọc s','m'),'Lc':('Chiều dài cọc Lc','m'),
    'Ec':('Mô đun đàn hồi cọc Ec','T/m²'),'Es':('Mô đun đàn hồi đất Es','T/m²'),
    'Es_used':('Es = 250 × Co','T/m²'),'Co_used':('Co của lớp đất chọn','T/m²'),
    'es_layer_no':('Số thứ tự lớp đất tính Es',''),'es_layer_name':('Tên lớp đất tính Es',''),
    'Ssoil_cm':('Lún đất giữa cọc Ssoil','cm'),'Scol_cm':('Lún cọc Scol','cm'),
    'differential_cm':('Chênh lún ΔS = |Ssoil − Scol|','cm'),'differential_limit_cm':('Giới hạn chênh lún [ΔS]','cm'),
    'differential_ok':('Kiểm tra chênh lún',''),'differential_checked':('Đã có giới hạn chênh lún',''),
    'S_total_cm':('Tổng độ lún S','cm'),'S1_cm':('Lún khối gia cố S1','cm'),'S2_cm':('Lún dưới mũi cọc S2','cm'),
    'Sc2_cm':('Lún cố kết dưới mũi cọc','cm'),'sum_sc':('Lún cố kết kiểm toán','cm'),'sum_si':('Lún tức thời','cm'),
    'total_s':('Tổng độ lún','cm'),'Psoil':('Ứng suất đất giữa cọc','T/m²'),'Pcol':('Ứng suất đầu cọc','T/m²'),
    'Eeq':('Mô đun đàn hồi tương đương','T/m²'),'ap':('Tỷ lệ diện tích thay thế ap',''),
    'sigma_p':('Ứng suất cọc σp','T/m²'),'sigma_s':('Ứng suất đất σs','T/m²'),
    'sigma_v_prime':('Ứng suất hữu hiệu σv′','T/m²'),'sigma_v':('Ứng suất σv','T/m²'),
    'qu_tt1':('Cường độ kiểm toán qu,TT1','T/m²'),'qu_allow':('Cường độ cọc cho phép','T/m²'),
    'qu_check':('Cường độ cọc dùng kiểm toán','T/m²'),'qu':('Cường độ cọc qu','T/m²'),'Rtc':('Sức chịu tải đất Rtc','T/m²'),
    'Fs':('Hệ số an toàn Fs',''),'qH':('Hoạt tải qH','T/m²'),'qT':('Tải trọng đắp qT','T/m²'),
    'Tr':('Lực kéo yêu cầu Tr','T/m'),'Td_fn':('Lực kéo cho phép Td/fn','T/m'),'Trp':('Lực kéo do võng','T/m'),
    'Tds':('Lực kéo do áp lực ngang','T/m'),'WT':('Lực gây võng','T/m'),'Td':('Sức chịu kéo thiết kế','T/m'),
    'shear':('Ứng suất cắt đệm','T/m²'),'shear_allow':('Ứng suất cắt cho phép','T/m²'),
    'sigma_k':('Ứng suất uốn có nền đàn hồi','T/m²'),'bending_allow':('Ứng suất uốn cho phép','T/m²'),
    'shear_ok':('Kiểm tra cắt thủng',''),'ok_k':('Kiểm tra uốn có nền đàn hồi',''),'pile_ok':('Kiểm tra cường độ cọc',''),
    'thickness':('Chiều dày','m'),'s_short':('Khoảng cách cạnh ngắn','m'),'pattern':('Sơ đồ bố trí',''),
    'pile_type':('Loại cọc',''),'scope':('Phạm vi xử lý',''),'n_layer':('Số lớp gia cường','lớp'),
    'H':('Chiều cao tính toán H','m'),'H_cdm':('Chiều cao tính toán CDM','m'),'H_tk':('Chiều cao thiết kế','m'),
    'H_tt':('Chiều cao tính toán Htt','m'),'H_bl':('Chiều cao bù lún','m'),'H_kcad':('Chiều cao kết cấu áo đường','m'),
    'day':('Thời điểm kiểm toán','ngày'),'wait_days':('Thời gian chờ','ngày'),'u_pct':('Độ cố kết U','%'),
    'max_wait_days':('Giới hạn ngày chờ','ngày'),'surcharge_height':('Chiều cao gia tải','m'),
    'hgh':('Chiều cao đắp giới hạn Hgh','m'),'drain_length':('Chiều sâu PVD/SD','m'),
    'Sc_cuối_cm':('Lún cố kết cuối Sc','cm'),'Sc_t_cm':('Lún cố kết tại t','cm'),
    'Sc_dư_cm':('Lún cố kết dư','cm'),'Si_cm':('Lún tức thời Si','cm'),'St_cm':('Tổng lún tại t','cm'),
    'St_cuối_cm':('Tổng lún cuối','cm'),'St_t_cm':('Tổng lún tại t','cm'),'U_%':('Độ cố kết U','%'),
    'Cv_cm2_ngày':('Hệ số cố kết Cv','cm²/ngày'),'C_t_m2':('Cường độ đất tại t','T/m²'),
    'Co_t_m2':('Cường độ đất Co','T/m²'),'Cv_cm2_ngày':('Hệ số cố kết Cv','cm²/ngày'),
    'cm':('Độ lún phân tố','cm'),'dp':('Gia tăng ứng suất Δp','T/m²'),'z0':('Đỉnh phân tố','m'),'z1':('Đáy phân tố','m'),
    'vị_trí':('Vị trí tính toán',''),'ngày':('Thời gian','ngày'),'name':('Tên thành phần',''),'layer':('Lớp đất',''),
    'Sc_lớp_cm':('Sc theo lớp','cm'),'Si_lớp_cm':('Si theo lớp','cm'),'St_lớp_cm':('St theo lớp','cm')}


def output_rows(value,path='',inherited_unit=''):
    """Flatten every native result leaf into readable rows without truncation or JSON."""
    rows=[]
    if isinstance(value,dict):
        for key,item in value.items():
            label,unit=OUTPUT_LABELS.get(key,(str(key).replace('_',' '),''))
            if not unit:
                unit='cm' if str(key).endswith('_cm') else 'm' if str(key).endswith('_m') else inherited_unit
            rows.extend(output_rows(item,(path+' / ' if path else '')+label,unit))
    elif isinstance(value,(list,tuple)):
        for index,item in enumerate(value):rows.extend(output_rows(item,path+' / '+str(index+1),inherited_unit))
        if not value:rows.append((path,'Không có',inherited_unit))
    else:
        if value is None:display='Chưa khai báo / chưa kiểm tra'
        elif isinstance(value,bool):display='Có / đạt' if value else 'Không / chưa đạt'
        elif isinstance(value,(int,float)):
            display=f'{value:.6g}' if math.isfinite(value) else 'Chưa có kết quả hữu hạn'
        else:display=str(value)
        rows.append((path,display,inherited_unit))
    return rows


def present_result(result):
    summary=result['summary']
    def number(value):
        try:return f'{float(value):.2f}' if math.isfinite(float(value)) else '—'
        except (ValueError,TypeError):return '—'
    design_keys=('excavation','bamboo','cajuput','cdm_lc','cdm_s','cdm_d','drain_length','drain_spacing','drain_diameter','surcharge_height','differential_cm','differential_limit_cm')
    columns=('Phương án / vị trí','Lún kiểm toán (cm)','Điều kiện lún','U (%)','Chờ (ngày)','t đánh giá (ngày)',
             'Đào sâu (m)','Cọc tre (m)','Cừ tràm (m)','Lc CDM (m)','s CDM (m)','D CDM (m)',
             'Sâu PVD/SD (m)','s PVD/SD (m)','d PVD/SD (cm)','Gia tải (m)','ΔS (cm)','[ΔS] (cm)','Kết quả')
    rows=[];errors=[];before_rows=[];check_rows=[];parameter_rows=[];detail_rows=[]
    def add(name,residual,limit,passed,details,design=None):
        design=design or {};sign='≤' if float(residual)<=float(limit) else '>'
        native=details.get('result',{})
        incomplete=native.get('differential_checked') is False
        status='CHƯA KIỂM TRA ΔS' if incomplete else 'ĐẠT' if passed else 'CHƯA ĐẠT'
        wait=details.get('wait_days');day=details.get('day',details.get('evaluation_day'))
        rows.append((name,number(residual),number(residual)+' '+sign+' '+number(limit),number(details.get('u_pct')),number(wait),number(day),
                     *[number(design.get(key,{}).get('value')) for key in design_keys],status))
    before=summary.get('before')
    if before:
        for loc in before['locations']:
            value=loc['Sc_dư_cm'];limit=before['limit_cm'];passed=value<=limit
            before_rows.append((loc['vị_trí'],number(loc['Sc_cuối_cm']),number(loc['Si_cm']),number(loc['St_cuối_cm']),number(loc['Sc_t_cm']),number(value),number(loc['U_%']),number(before['evaluation_day']),number(value)+(' ≤ ' if passed else ' > ')+number(limit),'ĐẠT' if passed else 'CHƯA ĐẠT'))
        add('Trước xử lý · '+before['scope'],before['residual_cm'],before['limit_cm'],before['pass_check'],{'evaluation_day':before['evaluation_day'],'u_pct':min(r['U_%'] for r in before['locations'])})
        detail_rows.extend(('Trước xử lý',*row) for row in output_rows(before))
    for check in summary.get('checks',[]):
        value=number(check.get('value'));limit=number(check.get('limit'));unit=check.get('unit','')
        if check.get('operator')=='>' and value==limit and check['passed']:value=repr(float(check['value']))
        condition=value+' '+check.get('operator','')+' '+limit+' '+unit if 'value' in check else 'Theo mô đun'
        check_rows.append((check['option'],check['check'],condition,'CHƯA KIỂM TRA' if check.get('checked') is False else 'ĐẠT' if check['passed'] else 'CHƯA ĐẠT'))
    if summary.get('tool')=='calculate':
        note='Trước xử lý · '+before['scope']+'; thời điểm đánh giá: '+number(before['evaluation_day'])+' ngày. Kết luận theo điều kiện lún dư Sc.'
    elif summary.get('tool')=='batch':
        for rec in result.get('records',[]):
            prefix='STT '+str(rec['section_no'])+' · '
            limit=rec['limit'];before=rec.get('before',{})
            if before:
                add(prefix+'Trước xử lý',before['total_cm'],limit,rec.get('before_pass',False),{})
                detail_rows.extend((prefix+'Trước xử lý',*row) for row in output_rows(before))
            for attempt in rec.get('attempts',[]):
                name=prefix+attempt['option']
                if attempt.get('error'):
                    errors.append((name,attempt['error']));continue
                details=attempt.get('calculation',{})
                from model import project_from_dict
                trial=project_from_dict(attempt['calculated_project'])
                design=design_parameters(attempt['option'],{'project':trial,'payload':attempt['payload'],'details':details})
                add(name,attempt['residual_cm'],attempt['limit_cm'],attempt['status']=='ĐẠT',details,design)
                for item in design.values():
                    raw=item['value'];display=number(raw) if isinstance(raw,(float,int)) else str(raw) if raw is not None else 'Chưa khai báo'
                    parameter_rows.append((name,item['label'],display,item['unit']))
                detail_rows.extend((name,*row) for row in output_rows(details))
                check_rows.append((name,'Lún kiểm toán',number(attempt['residual_cm'])+(' ≤ ' if attempt['residual_cm']<=limit else ' > ')+number(limit)+' cm',attempt['status']))
        errors.extend(('STT '+str(item['section_no']),item['reason']) for item in summary.get('failures',[]))
        note=('Kết quả đã cập nhật trong bảng tổng hợp.' if not summary.get('output_folder') else 'Kết quả xuất: '+summary['output_folder'])
    else:
        for attempt in summary.get('attempts',[]):
            if attempt.get('error'):
                errors.append((attempt['option'],attempt['error']))
                rows.append((attempt['option'],)+('—',)*(len(columns)-2)+('CHƯA TÍNH ĐƯỢC',));continue
            details=attempt.get('calculation',{});design=attempt.get('design',{})
            add(attempt['option'],attempt['residual_cm'],attempt['limit_cm'],attempt['pass_check'],details,design)
            for item in design.values():
                raw=item['value'];display=number(raw) if isinstance(raw,(float,int)) else str(raw) if raw is not None else 'Chưa khai báo'
                parameter_rows.append((attempt['option'],item['label'],display,item['unit']))
            detail_rows.extend((attempt['option'],*row) for row in output_rows(details))
            if details.get('result',{}).get('differential_checked') is False:errors.append((attempt['option'],'Chưa nhập giới hạn chênh lún [ΔS] tại ALiCC.'))
        note=summary.get('recommendation','')+' '+summary.get('criterion','')+'.\nChờ là thời gian chờ bổ sung; t đánh giá gồm tiến độ thi công. Xem Thông số phương án và Chi tiết kết quả để đọc toàn bộ đầu ra.'
    if summary.get('limit_source'):
        note += '\nĐộ lún cho phép [ΔS] lấy trực tiếp từ Data: ' + summary['limit_source'] + '.'
    overview=note+'\n'+'\n'.join(row[0]+': '+row[-1]+'; lún '+row[1]+' cm; '+row[2]+' cm.' for row in rows)
    return {'columns':columns,'rows':rows,'quantities':[],'errors':errors,'note':note,'overview':overview,
            'before_columns':('Vị trí','Sc cuối (cm)','Si (cm)','St cuối (cm)','Sc(t) (cm)','Sc dư (cm)','U (%)','t (ngày)','Điều kiện Sc dư','Kết quả'),
            'before_rows':before_rows,'check_rows':check_rows,'parameter_rows':parameter_rows,'detail_rows':detail_rows}
