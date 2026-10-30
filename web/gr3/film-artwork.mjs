// Large packaging faces and separately drawn compact sprites share one identity.
export function filmArtwork(film,compact=false){
 return (compact?film?.icon_compact_url:film?.icon_url)||film?.icon_url||'';
}

export function pickerArtwork(option){
 const {icon,iconCompact}=option.dataset;
 return iconCompact||(icon||'').replace(/^(\/gr3\/film-icons\/\d+)-large\.png(?=\?|$)/,'$1.png');
}

const escapeText=value=>value.replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[ch]));
export function customFilmArtwork(value){
 const name=String(value||'LUT').slice(0,23);
 let hash=2166136261;for(const ch of name)hash=Math.imul(hash^ch.charCodeAt(0),16777619)>>>0;
 const colors=['#244f63','#735065','#8b552d','#38634e','#783b40','#3c5079','#6d4d68','#655b43'];
 const color=colors[hash%colors.length],words=name.split(/\s+/),lines=[''];
 for(const word of words){const i=lines.length-1;if(lines[i]&&lines[i].length+word.length>11)lines.push(word);else lines[i]+=(lines[i]?' ':'')+word;}
 const labels=lines.flatMap(line=>line.match(/.{1,11}/g)||[]).slice(0,3);
 const text=labels.map((line,i)=>`<text x="12" y="${57+i*21}" font-size="${line.length>8?14:18}">${escapeText(line)}</text>`).join('');
 const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><rect x="1" y="1" width="126" height="126" rx="3" fill="${color}" stroke="#ddcda5"/><path d="M34 127Q105 113 127 38V127Z" fill="#ead7b0" opacity=".2"/><path d="M75 127Q115 110 127 78V127Z" fill="#ead7b0" opacity=".2"/><g fill="#fff5df" font-family="sans-serif" font-weight="700"><text x="12" y="25" font-size="11">M10V · LUT</text>${text}</g><path d="M12 113H116" stroke="#e6c990" stroke-width="5"/></svg>`;
 return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
}
