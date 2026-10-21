#!/usr/bin/env node









'use strict';
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  WidthType, HeadingLevel, AlignmentType, InternalHyperlink, BookmarkStart, BookmarkEnd, ShadingType,
} = require('docx');

const FONT = 'Microsoft YaHei';
const CW = 9026; 
const MAX_W = 560, MAX_H = 760; 

const r = (t, o = {}) => new TextRun({ text: t, font: FONT, size: o.size || 21,
  bold: o.bold, color: o.color, italics: o.italics });
const P = (children, o = {}) => new Paragraph({
  children: Array.isArray(children) ? children : [r(children, o)],
  alignment: o.align, spacing: o.spacing, heading: o.heading, bullet: o.bullet,
  pageBreakBefore: o.pb, indent: o.indent });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 240, after: 120 },
  children: [r(t, { size: 30, bold: true, color: 'C0392B' })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 100 },
  children: [r(t, { size: 24, bold: true, color: '8E44AD' })] });
const cb = (t) => new Paragraph({ bullet: { level: 0 }, children: [r('☐  ' + t, { size: 21 })] });

function secHeading(title, idx) {
  return new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1,
    children: [
      new BookmarkStart('sec' + idx, idx),
      r(title, { size: 32, bold: true, color: 'C0392B' }),
      new BookmarkEnd(idx),
    ] });
}


function imgDims(file) {
  const b = fs.readFileSync(file);
  if (b[0] === 0x89 && b[1] === 0x50) { 
    return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
  }
  if (b[0] === 0xFF && b[1] === 0xD8) { 
    for (let i = 2; i < b.length - 9;) {
      if (b[i] !== 0xFF) { i++; continue; }
      const m = b[i + 1];
      if (m >= 0xC0 && m <= 0xCF && m !== 0xC4 && m !== 0xC8 && m !== 0xCC) {
        return { w: b.readUInt16BE(i + 7), h: b.readUInt16BE(i + 5) };
      }
      i += 2 + b.readUInt16BE(i + 2);
    }
  }
  throw new Error('无法识别的图片格式: ' + file);
}
function scaled(dims, override) {
  let { w, h } = dims;
  if (override && override.w) { w = override.w; h = override.h; }
  else {
    const s = Math.min(MAX_W / w, MAX_H / h, 1);
    if (s < 1) { w = Math.round(w * s); h = Math.round(h * s); }
  }
  return { w, h };
}
function imgP(imgPath, override) {
  const { w, h } = scaled(imgDims(imgPath), override);
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100, after: 100 },
    children: [new ImageRun({ data: fs.readFileSync(imgPath), type: 'jpg', transformation: { width: w, height: h } })] });
}


function cell(text, w, { bold, fill } = {}) {
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: fill ? { fill, color: 'auto', type: ShadingType.CLEAR } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ alignment: AlignmentType.LEFT, children: [r(String(text), { bold, size: 20 })] })],
  });
}
function T(headers, rows, widths, headerFill = 'FDEBD0') {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({ width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, widths[i], { bold: true, fill: headerFill })) }),
      ...rows.map((rr) => new TableRow({ children: rr.map((c, i) => cell(c, widths[i])) })),
    ] });
}


function renderSection(s, imgs, idx) {
  const out = [];
  switch (s.type) {
    case 'cards':
      out.push(secHeading(s.title, idx));
      out.push(imgP(imgs(s.img), s));
      if (s.caption) out.push(P(s.caption, { size: 20, color: '8A6D3B', align: AlignmentType.CENTER }));
      break;
    case 'overview':
      out.push(secHeading(s.title, idx));
      out.push(imgP(imgs(s.img), s));
      if (s.caption) out.push(P(s.caption, { size: 20, color: '8A6D3B', align: AlignmentType.CENTER }));
      break;
    case 'daymaps':
      out.push(secHeading(s.title, idx));
      for (const d of s.days) {
        out.push(H2(d.h2));
        out.push(imgP(imgs(d.img), d));
      }
      break;
    case 'table':
      out.push(secHeading(s.title, idx));
      if (s.intro) out.push(P(s.intro, { size: 20, color: '8A6D3B' }));
      out.push(T(s.headers, s.rows, s.widths));
      if (s.note) out.push(P(s.note, { size: 20, color: 'C0392B', bold: true, spacing: { before: 160 } }));
      break;
    case 'tables':
      out.push(secHeading(s.title, idx));
      for (const g of s.groups) {
        out.push(H2(g.h2));
        out.push(T(g.headers, g.rows, g.widths));
      }
      break;
    case 'itinerary':
      out.push(secHeading(s.title, idx));
      for (const d of s.days) {
        out.push(H2(d.h2));
        out.push(...d.lines.map((t) => P(t, { spacing: { after: 60 } })));
      }
      break;
    case 'checklist':
      out.push(secHeading(s.title, idx));
      out.push(...s.items.map((t) => cb(t)));
      break;
    case 'list':
      out.push(secHeading(s.title, idx));
      out.push(...s.items.map((t) => P(t, { spacing: { after: 80 } })));
      break;
    default:
      throw new Error('未知章节类型: ' + s.type);
  }
  return out;
}

function main() {
  const contentFile = process.argv[2] || 'content.json';
  const outFile = process.argv[3];
  const content = JSON.parse(fs.readFileSync(contentFile, 'utf8'));
  const baseDir = path.dirname(path.resolve(contentFile));
  const imgDir = path.join(baseDir, content.images_dir || 'jpg');
  const imgs = (name) => path.join(imgDir, name);

  const doc = [];
  
  const cv = content.cover || {};
  if (cv.city) {
    doc.push(
      new Paragraph({ spacing: { before: 900 }, alignment: AlignmentType.CENTER, children: [r(cv.city, { size: 72, bold: true, color: 'C0392B' })] }),
      new Paragraph({ spacing: { before: 120 }, alignment: AlignmentType.CENTER, children: [r(cv.title || '', { size: 40, bold: true, color: '3D2B1F' })] }),
      new Paragraph({ spacing: { before: 260 }, alignment: AlignmentType.CENTER, children: [r(cv.dates || '', { size: 26, color: '8A6D3B' })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, children: [r(cv.people || '', { size: 24, color: '8A6D3B' })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, children: [r(cv.budget || '', { size: 24, color: 'C0392B', bold: true })] }),
      new Paragraph({ spacing: { before: 300 }, alignment: AlignmentType.CENTER, children: [r(cv.theme || '', { size: 22, color: '5D4037' })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, children: [r(cv.stay || '', { size: 22, color: '5D4037' })] }),
      new Paragraph({ spacing: { before: 1200 }, alignment: AlignmentType.CENTER, children: [r('底图 © 高德地图 ｜ 照片 © Wikimedia Commons（CC协议）', { size: 16, color: '999999' })] }),
    );
  }
  
  doc.push(
    new Paragraph({ pageBreakBefore: true, spacing: { after: 240 }, children: [r('目录', { size: 32, bold: true, color: 'C0392B' })] }),
  );
  (content.sections || []).forEach((s, i) => {
    doc.push(new Paragraph({ spacing: { before: 140 },
      children: [new InternalHyperlink({ anchor: 'sec' + i, children: [r('▸ ' + s.title, { size: 24, color: '2E86C1' })] })] }));
  });
  doc.push(new Paragraph({ spacing: { before: 200 }, children: [r(content.toc_note || '※ 点击目录条目可跳转到对应章节。', { size: 18, color: '999999' })] }));
  
  for (let i = 0; i < (content.sections || []).length; i++) doc.push(...renderSection(content.sections[i], imgs, i));
  
  for (const n of content.notes || []) doc.push(new Paragraph({ spacing: { before: 200 }, children: [r(n, { size: 18, color: '999999' })] }));

  const document = new Document({
    creator: 'Travel Guide',
    title: (cv.city || '') + ' ' + (cv.title || '') + '攻略',
    styles: { default: { document: { run: { font: FONT, size: 21 } } } },
    features: { updateFields: true },
    sections: [{
      properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
      children: doc,
    }],
  });

  Packer.toBuffer(document).then((buf) => {
    const out = path.resolve(outFile || content.out || '攻略.docx');
    fs.writeFileSync(out, buf);
    console.log('written', out, (buf.length / 1024 / 1024).toFixed(1) + 'MB');
  });
}

main();
