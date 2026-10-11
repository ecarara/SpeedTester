// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Edson Angelo Carara

/* Dependency-free interactive SVG charts, matching the dashboard palette. */
(() => {
  const NS='http://www.w3.org/2000/svg', colors={download:'#d8ff66',upload:'#ffad68',contract:'#6de4d0',muted:'#8da9a1'};
  function el(tag,attrs={},text='') {
    const node=document.createElementNS(NS,tag);
    Object.entries(attrs).forEach(([key,value])=>node.setAttribute(key,String(value)));
    if(text)node.textContent=text;
    return node;
  }
  function base(target,title) {
    target.replaceChildren();
    const svg=el('svg',{viewBox:'0 0 820 330',role:'img','aria-label':title,width:'100%'});
    target.append(svg);return svg;
  }
  function axes(svg,maxY,xlabels) {
    for(let i=0;i<=4;i++) {
      const y=285-i*61;
      svg.append(el('line',{x1:85,y1:y,x2:800,y2:y,stroke:'#26413e'}));
      svg.append(el('text',{x:76,y:y+4,fill:colors.muted,'font-size':11,'text-anchor':'end'},Math.round(maxY*i/4)+' Mbps'));
    }
    xlabels.forEach(({x,label})=>{
      let anchor='middle';
      if(x<120)anchor='start';
      if(x>740)anchor='end';
      svg.append(el('text',{x,y:313,fill:colors.muted,'font-size':11,'text-anchor':anchor},label));
    });
  }
  function renderSpeed(target,rows,contract,zone='America/Sao_Paulo') {
    const svg=base(target,'Velocidade ao longo do tempo: download, upload e contrato'), good=rows.filter(row=>!row.is_failure&&row.download_mbps!=null).sort((a,b)=>Date.parse(a.started_at)-Date.parse(b.started_at));
    if(!good.length){svg.append(el('text',{x:410,y:165,fill:colors.muted,'text-anchor':'middle'},'Sem medições representativas no período'));return;}
    const start=Date.parse(good[0].started_at), finish=Date.parse(good.at(-1).started_at), span=Math.max(finish-start,1),maxY=Math.max(...good.map(row=>Number(row.download_mbps)||0),...good.map(row=>Number(row.upload_mbps)||0),Number(contract)||0,1)*1.12;
    const x=value=>85+(Date.parse(value)-start)/span*715,y=value=>285-Number(value)/maxY*244;
    const dateFormatter=new Intl.DateTimeFormat('pt-BR',{timeZone:zone,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
    axes(svg,maxY,[0,.25,.5,.75,1].map(f=>({x:85+715*f,label:dateFormatter.format(new Date(start+span*f))})));
    if(contract)svg.append(el('line',{x1:85,y1:y(contract),x2:800,y2:y(contract),stroke:colors.contract,'stroke-dasharray':'6 5'}));
    ['download','upload'].forEach(metric=>{
      // Split at failures/missing values instead of drawing through outages.
      let points=[];
      function flush(){if(points.length){svg.append(el('polyline',{points:points.join(' '),fill:'none',stroke:colors[metric],'stroke-width':2}));}points=[];}
      rows.slice().sort((a,b)=>Date.parse(a.started_at)-Date.parse(b.started_at)).forEach(row=>{
        const value=row[metric+'_mbps'];if(row.is_failure||value==null){flush();return;}
        points.push(x(row.started_at)+','+y(value));
      });flush();
      good.filter(row=>row[metric+'_mbps']!=null).forEach(row=>{
        const label=dateFormatter.format(new Date(row.started_at))+' · '+metric+': '+Number(row[metric+'_mbps']).toFixed(2)+' Mbps';
        const point=el('circle',{cx:x(row.started_at),cy:y(row[metric+'_mbps']),r:3.8,fill:colors[metric],tabindex:0,'aria-label':label});
        point.append(el('title',{},label));
        const describe=()=>{document.getElementById('chartDetail').textContent=label;};
        point.addEventListener('pointerenter',describe);point.addEventListener('focus',describe);svg.append(point);
      });
    });
  }
  function renderDistribution(target,metrics) {
    const svg=base(target,'Distribuição de download por quadrante: p10, mediana e p95'), labels={madrugada:'Madrugada',manha:'Manhã',tarde:'Tarde',noite:'Noite'};
    const maxY=Math.max(...Object.values(metrics).map(row=>row.download_p95_mbps||row.download_avg_mbps||0),1)*1.12,y=value=>285-Number(value)/maxY*244;
    axes(svg,maxY,[]);
    Object.entries(labels).forEach(([key,label],index)=>{
      const row=metrics[key]||{},x=145+index*185;
      svg.append(el('text',{x,y:313,fill:colors.muted,'font-size':13,'text-anchor':'middle'},label));
      if(!row.count){svg.append(el('text',{x,y:160,fill:colors.muted,'font-size':12,'text-anchor':'middle'},'Sem dados'));return;}
      const low=row.download_p10_mbps??row.download_avg_mbps,high=row.download_p95_mbps??row.download_avg_mbps,median=row.download_median_mbps??row.download_avg_mbps;
      svg.append(el('line',{x1:x,y1:y(low),x2:x,y2:y(high),stroke:colors.contract,'stroke-width':3}));
      svg.append(el('rect',{x:x-26,y:y(high),width:52,height:Math.max(y(low)-y(high),2),fill:'#6de4d022',stroke:colors.contract,rx:5}));
      svg.append(el('line',{x1:x-26,y1:y(median),x2:x+26,y2:y(median),stroke:colors.download,'stroke-width':4}));
      svg.append(el('text',{x,y:y(high)-12,fill:colors.download,'font-size':11,'text-anchor':'middle'},Number(median).toFixed(1)+' · n='+row.count));
      const title=el('title',{},label+': p10 '+low+', mediana '+median+', p95 '+high+' Mbps');svg.append(title);
    });
  }
  window.SpeedTesterCharts={renderSpeed,renderDistribution};
})();
