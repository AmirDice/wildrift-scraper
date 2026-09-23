/** Single-target timeline, mirrored by web/hwei.py. See hwei_kit assumptions. */
/* eslint-disable @typescript-eslint/no-explicit-any */
export function hweiTimeline(kit: any, st: any, target: any, window: number, level = 13) {
  const choices: Record<string, string> = { "1": "QQ", "2": "WE", "3": "EQ", ...st.hweiChoices };
  for (const [slot, valid] of Object.entries({"1":["QQ","QW","QE"],"2":["WQ","WW","WE"],"3":["EQ","EW","EE"]}))
    if (!valid.includes(choices[slot])) throw new Error("Invalid Hwei subject choice");
  const ranks: Record<string, number> = Object.fromEntries(Object.entries<number[]>(kit.skillOrder)
    .map(([s, levels]) => [s, levels.filter(lv => lv <= level).length - 1]));
  const value = (xs: number[], rank: number): number => xs[Math.min(Math.max(rank, 0), xs.length - 1)];
  const ap = st.ap ?? 0, haste = 100 / (100 + (st.haste ?? 0));
  const result = {damage: {P:0,"1":0,"2":0,"3":0,"4":0} as Record<string,number>,
    casts: {"1":0,"2":0,"3":0,"4":0} as Record<string,number>, autos:0, passives:0,
    empoweredHits:0, manaRestored:0, shield:0, allyShield:0, manaRemaining:0,
    events: [] as {time:number; slot:string; damage:number}[]};
  const queue: {t:number; serial:number; kind:string; data:any}[] = [];
  let serial = 0;
  const push = (t:number, kind:string, data:any = null) => { queue.push({t,serial:++serial,kind,data}); };
  const ready: Record<string,number> = {"1":0,"2":0,"3":0,"4":0};
  let mana = st.mana ?? 0;
  const manaMax = mana;
  let lastTime = 0, nextAuto = 0, charges = 0, lightId = "", markUntil = -1, dealt = 0;
  let marked: string | null = null;
  const seen = new Set<string>(), empowered = new Set<string>();
  const shieldCasts: [number,number][] = [];
  const hit = (t:number, slot:string, token:string, amount:number, useLights=true) => {
    result.damage[slot] += amount; dealt += amount;
    result.events.push({time:Math.round(t*10000)/10000,slot,damage:amount});
    if (!seen.has(token) && amount > 0) {
      seen.add(token);
      if (marked !== null && t <= markUntil && marked !== token) {
        marked = null;
        const p = kit.passive;
        push(t+0.25,"passive",p.base[0]+(p.base[1]-p.base[0])*(level-1)/14+p.ap*ap);
      } else { marked = token; markUntil = t+kit.passive.markSeconds; }
    }
    if (useLights && charges && !empowered.has(token)) {
      empowered.add(token); charges--;
      const we = kit.spells.WE, restore = value(we.manaRestore,ranks["2"]);
      mana = Math.min(manaMax,mana+restore); result.manaRestored += restore; result.empoweredHits++;
      hit(t,"2",lightId,value(we.base,ranks["2"])+we.ap*ap,false);
    }
  };
  push(0,"action");
  while (queue.length) {
    queue.sort((a,b)=>a.t-b.t || a.serial-b.serial);
    const {t,kind,data} = queue.shift()!;
    if (t > window+1e-9) break;
    const regen = kit.baseStats.manaRegen;
    mana = Math.min(manaMax,mana+(t-lastTime)*(regen[0]+regen[1]*(level-1))/5); lastTime=t;
    if (kind === "passive") { result.damage.P+=data; result.passives++; dealt+=data; continue; }
    if (kind === "hit") { hit(t,data[0],data[1],data[2]); continue; }
    if (kind === "bolt") {
      const [slot,token,spell,rank] = data;
      const missing = Math.min(1,Math.max(0,1-(target.currentHp??target.hp)/target.hp+dealt*(target.magicMultiplier??1)/target.hp));
      const low=value(spell.base,rank)+spell.ap*ap, high=value(spell.maxBase,rank)+spell.maxAp*ap;
      hit(t,slot,token,low+(high-low)*missing); continue;
    }
    const slot=["2","3","1","4"].find(s=>ranks[s]>=0 && ready[s]<=t+1e-9 && mana>=kit.manaCosts[s]);
    if (slot !== undefined) {
      const rank=ranks[slot], code=slot==="4"?"R":choices[slot], spell=kit.spells[code];
      result.casts[slot]++;
      const token=slot+":"+result.casts[slot], impact=t+0.25;
      mana-=kit.manaCosts[slot]; ready[slot]=t+value(kit.cooldowns[slot],rank)*haste;
      if(code==="WE") { charges=spell.charges; lightId=token; }
      else if(code==="WW") shieldCasts.push([t,rank]);
      else if(code==="WQ") { /* Stationary target: movement and vision omitted. */ }
      else if(code==="QW") push(impact,"bolt",[slot,token,spell,rank]);
      else {
        let base=value(spell.base,rank)+spell.ap*ap;
        if(code==="QQ") base+=value(spell.targetMaxHp,rank)*target.hp;
        push(impact+(code==="R"?spell.duration:0),"hit",[slot,token,base]);
        if(code==="QE" || code==="R") {
          const tick=value(spell.tickBase,rank)+spell.tickAp*ap, step=code==="QE"?0.5:1;
          for(let i=1;i<=Math.round(spell.duration/step);i++) push(impact+i*step,"hit",[slot,token,tick*step]);
        }
      }
    } else if(nextAuto<=t+1e-9) {
      result.autos++; nextAuto=t+1/Math.max(st.as??0.75,0.1);
      if(charges) {
        empowered.add("auto:"+result.autos); charges--;
        const we=kit.spells.WE, restore=value(we.manaRestore,ranks["2"]);
        mana=Math.min(manaMax,mana+restore); result.manaRestored+=restore; result.empoweredHits++;
        hit(t,"2",lightId,value(we.base,ranks["2"])+we.ap*ap,false);
      }
    }
    push(t+0.45,"action");
  }
  for(const [t,rank] of shieldCasts) {
    const ww=kit.spells.WW, initial=value(ww.shieldBase,rank)+ww.shieldAp*ap;
    const cap=value(ww.maxShieldBase,rank)+ww.maxShieldAp*ap;
    const shield=initial+(cap-initial)*Math.min(1,Math.max(0,window-t)/ww.rampSeconds);
    result.shield+=shield; result.allyShield+=shield*ww.allyMultiplier;
  }
  result.manaRemaining=mana;
  return result;
}
