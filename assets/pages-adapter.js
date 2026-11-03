'use strict';
// GitHub Pages runs this viewer in the browser. It does not run Flask or MySQL.
(() => {
  const dataset = fetch(new URL('./demo-data.json', document.baseURI)).then(r => {
    if (!r.ok) throw new Error('演示数据未能加载，请刷新页面。');
    return r.json();
  });
  const json = (value, status = 200) => new Response(JSON.stringify(value), {
    status, headers: {'Content-Type': 'application/json; charset=utf-8'}
  });
  const eventKey = row => JSON.stringify([row.kh, row.dtime, row.syjh, row.djh]);
  const sum = rows => rows.reduce((total, row) => total + Number(row.amount_cents), 0);
  function customers(data, query) {
    const kh = (query.get('kh') || '').trim();
    const segment = query.get('segment') || '';
    const sort = query.get('sort') || 'm';
    if (kh && !/^[0-9a-fA-F]{1,8}$/.test(kh)) throw new Error('客户标识请输入1—8位十六进制字符。');
    if (segment && !data.summary.segments.some(s => s.code === segment)) throw new Error('分群参数无效。');
    if (!['m', 'f', 'r', 'kh'].includes(sort)) throw new Error('排序参数无效。');
    const rows = data.customers.filter(row => (!kh || row.kh.includes(kh)) && (!segment || row.segment_code === segment));
    rows.sort((a, b) => (sort === 'm' ? b.m_cents - a.m_cents : sort === 'f' ? b.f - a.f : sort === 'r' ? a.r - b.r : 0) || a.kh.localeCompare(b.kh));
    return rows;
  }
  function sales(data, query) {
    const start = query.get('start') || data.summary.start;
    const end = query.get('end') || data.summary.end;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || start >= end || start < data.summary.start || end > data.summary.end) throw new Error('筛选日期须位于演示批次的观察窗口内，且开始日小于结束日。');
    const rows = data.lines.filter(row => row.dtime.slice(0, 10) >= start && row.dtime.slice(0, 10) < end);
    const months = new Map();
    rows.forEach(row => {
      const month = row.dtime.slice(0, 7);
      if (!months.has(month)) months.set(month, {month, amount_cents: 0, details: 0, keys: new Set()});
      const entry = months.get(month); entry.amount_cents += row.amount_cents; entry.details++; entry.keys.add(eventKey(row));
    });
    function ranking(key) {
      const groups = new Map();
      rows.forEach(row => {
        const name = row[key] || '未提供';
        if (!groups.has(name)) groups.set(name, {name, label: row.spmc, amount_cents: 0, details: 0});
        const entry = groups.get(name); entry.amount_cents += row.amount_cents; entry.details++;
      });
      return [...groups.values()].sort((a, b) => b.amount_cents - a.amount_cents || a.name.localeCompare(b.name)).slice(0, 10);
    }
    return {
      totals: {detail_count: rows.length, customer_count: new Set(rows.map(r => r.kh)).size,
        amount_cents: sum(rows), event_count: new Set(rows.map(eventKey)).size},
      monthly: [...months.values()].sort((a, b) => a.month.localeCompare(b.month)).map(({keys, ...row}) => ({...row, events: keys.size})),
      products: ranking('spbm'), counters: ranking('gzmc'), start, end, batch_id: data.batch.id
    };
  }
  window.demoRequest = async (input, options = {}) => {
    try {
      if ((options.method || 'GET').toUpperCase() !== 'GET') return json({error: '此为网页演示版，上传分析请在完整本机系统中操作。'}, 403);
      const data = await dataset;
      const url = new URL(input, location.origin);
      const path = url.pathname;
      const query = url.searchParams;
      if (query.has('batch_id') && query.get('batch_id') !== data.batch.id) return json({error: '演示批次不存在。'}, 404);
      if (path === '/api/health') return json({status: 'demo', database: null});
      if (path === '/api/summary') return json({batch: data.batch, summary: data.summary});
      if (path === '/api/sales') return json(sales(data, query));
      if (path === '/api/batches') return json({items: [data.batch], active_batch_id: data.batch.id});
      if (path === '/api/batches/' + data.batch.id) return json(data.batch);
      if (path === '/api/customers') {
        const rows = customers(data, query);
        const page = Number(query.get('page') || 1), pageSize = Number(query.get('page_size') || 20);
        if (!Number.isInteger(page) || page < 1 || !Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) throw new Error('分页参数无效。');
        return json({items: rows.slice((page - 1) * pageSize, page * pageSize), total: rows.length, page, page_size: pageSize, batch_id: data.batch.id});
      }
      if (path.startsWith('/api/customers/')) {
        const kh = decodeURIComponent(path.split('/').pop());
        const customer = data.customers.find(row => row.kh === kh);
        if (!customer) return json({error: '未找到此演示客户。'}, 404);
        const page = Number(query.get('page') || 1);
        if (!Number.isInteger(page) || page < 1) throw new Error('明细页码无效。');
        const rows = data.lines.filter(row => row.kh === kh).sort((a, b) => b.dtime.localeCompare(a.dtime) || a.source_row - b.source_row);
        return json({customer, lines: rows.slice((page - 1) * 20, page * 20), page, page_size: 20, reference: data.summary.reference});
      }
      if (path === '/api/export') {
        if (query.get('format') !== 'csv') throw new Error('网页演示支持CSV导出；Excel导出请使用完整系统。');
        const header = ['客户标识', '最近购买时间', 'R_天', 'F_购买事件数', 'M_正向购买金额_元', '商品明细数', 'R评分', 'F评分', 'M评分', '客户分群', '分群编码', '分析批次', '窗口开始_含', '窗口结束_不含', '分析基准日', '规则版本', '数据说明'];
        const rows = customers(data, query).map(row => [row.kh, row.last_purchase, row.r, row.f, (row.m_cents / 100).toFixed(2), row.detail_count, row.r_score, row.f_score, row.m_score, row.segment, row.segment_code, data.batch.id, data.summary.start, data.summary.end, data.summary.reference, 'rfm-v1', '自编演示数据，非论文研究样本']);
        const escape = value => '"' + String(value).replace(/"/g, '""') + '"';
        return new Response('\ufeff' + [header, ...rows].map(row => row.map(escape).join(',')).join('\r\n'), {headers: {'Content-Type': 'text/csv; charset=utf-8'}});
      }
      return json({error: '此功能未包含在网页演示中。'}, 404);
    } catch (error) { return json({error: error.message || '演示数据处理失败。'}, 400); }
  };
})();
