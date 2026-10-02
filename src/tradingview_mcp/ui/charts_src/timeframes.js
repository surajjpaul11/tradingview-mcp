const MINUTE = 60;
const HOUR = 3600;
export const DAY = 86400;
export const RESOLUTIONS = [
  { id:'1m',label:'1m',seconds:MINUTE }, { id:'30m',label:'30m',seconds:30*MINUTE },
  { id:'1h',label:'1h',seconds:HOUR }, { id:'2h',label:'2h',seconds:2*HOUR },
  { id:'4h',label:'4h',seconds:4*HOUR }, { id:'12h',label:'12h',seconds:12*HOUR },
  { id:'1d',label:'1D',seconds:DAY }, { id:'5d',label:'5D',seconds:5*DAY },
];
export const RANGES = [
  { id:'1D',label:'1D',period:'1d',seconds:DAY }, { id:'1W',label:'1W',period:'5d',seconds:7*DAY },
  { id:'1M',label:'1M',period:'1mo',seconds:30*DAY }, { id:'3M',label:'3M',period:'3mo',seconds:90*DAY },
  { id:'1Y',label:'1Y',period:'1y',seconds:365*DAY }, { id:'5Y',label:'5Y',period:'5y',seconds:5*365*DAY },
  { id:'MAX',label:'Max',period:'max',seconds:null },
];
export const findResolution=(id)=>RESOLUTIONS.find((item)=>item.id===id) ?? RESOLUTIONS[0];
export const findRange=(id)=>RANGES.find((item)=>item.id===id) ?? RANGES[0];
const MIN_BARS=3;
const HL_MAX=5000;
const YAHOO_LIMIT={ '1m':7, '30m':60, '1h':730, '2h':730, '4h':730, '12h':730 };
export function getAvailability(source,resolutionId,rangeId){
  const resolution=findResolution(resolutionId); const range=findRange(rangeId);
  if(range.seconds===null) return {available:true,reason:''};
  const bars=range.seconds/resolution.seconds;
  if(bars<MIN_BARS) return {available:false,reason:`${range.label} has fewer than ${MIN_BARS} candles`};
  if(source==='hyperliquid' && bars>HL_MAX) return {available:false,reason:'Hyperliquid keeps the latest 5,000 candles'};
  const limit=YAHOO_LIMIT[resolutionId];
  if(source==='yahoo' && limit && range.seconds>limit*DAY) return {available:false,reason:`Yahoo limits ${resolution.label} history to ${limit} days`};
  return {available:true,reason:''};
}
export function resolveResolution(source,resolutionId,rangeId){
  if(getAvailability(source,resolutionId,rangeId).available) return resolutionId;
  const current=RESOLUTIONS.findIndex((item)=>item.id===resolutionId);
  return [...RESOLUTIONS].sort((a,b)=>Math.abs(RESOLUTIONS.indexOf(a)-current)-Math.abs(RESOLUTIONS.indexOf(b)-current) || b.seconds-a.seconds)
    .find((item)=>getAvailability(source,item.id,rangeId).available)?.id ?? resolutionId;
}
const option=(item,a)=>({id:item.id,label:item.label,disabled:!a.available,title:a.reason});
export const resolutionOptions=(source,rangeId)=>RESOLUTIONS.map((item)=>option(item,getAvailability(source,item.id,rangeId)));
export const rangeOptions=(source,resolutionId)=>RANGES.map((item)=>option(item,getAvailability(source,resolutionId,item.id)));
