"""Real Chromium UI verification. Requires the server and playwright chromium."""
from pathlib import Path
import json
import sys
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/系统截图'
OUT.mkdir(exist_ok=True)

def main():
    errors=[];checks=[]
    def check(name,condition):
        assert condition,name
        checks.append({'check':name,'passed':True})
        print('PASS',name,flush=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1080},device_scale_factor=1)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('http://127.0.0.1:5000/',wait_until='networkidle')
        page.wait_for_function("document.getElementById('metric-lines').textContent === '356,346'")
        check('销售卡片使用实际金额和明细',page.locator('#metric-amount').inner_text()=='515,985,850.95' and page.locator('#metric-events').inner_text()=='186,971')
        check('全部图表实例加载',page.evaluate("Object.keys(state.charts).length") == 4)
        page.screenshot(path=str(OUT/'01_销售概览.png'),full_page=True)
        page.locator('[data-nav="segments"]').click()
        page.wait_for_timeout(400)
        check('分群页面真实人数',page.locator('#segment-total').inner_text()=='47,597')
        check('八种群体均展示',page.locator('#segments-body tr').count()==8)
        check('页面切换后可见图表宽度正常',page.evaluate("['chart-segments','chart-contribution'].every(id=>state.charts[id].getWidth()>100)"))
        page.screenshot(path=str(OUT/'02_RFM分群.png'),full_page=True)
        page.locator('[data-nav="customers"]').click()
        page.wait_for_function("document.querySelectorAll('#customers-body [data-customer]').length === 40")
        check('客户分页默认20条',page.locator('#customers-body tr').count()==20)
        kh=page.locator('#customers-body [data-customer]').first.get_attribute('data-customer')
        page.locator('#customers-body [data-customer]').first.click()
        page.locator('#customer-dialog .detail-summary').wait_for()
        check('客户详情追查购买记录',page.locator('#customer-dialog table tbody tr').count()>0)
        page.screenshot(path=str(OUT/'04_客户详情.png'),full_page=True)
        page.locator('#close-dialog').click()
        page.locator('#customer-kh').fill(kh)
        with page.expect_response(lambda r:'/api/customers?' in r.url and r.status==200):
            page.locator('#customer-filter button[type="submit"]').click()
        page.wait_for_function("document.querySelectorAll('#customers-body tr').length===1")
        check('客户标识筛选实际生效',kh in page.locator('#customers-body').inner_text())
        with page.expect_download() as download:
            page.locator('[data-format="csv"]').click()
        saved=ROOT/'docs/验证输出/浏览器客户筛选导出.csv'
        download.value.save_as(saved)
        check('浏览器下载筛选结果',kh in saved.read_text(encoding='utf-8-sig') and len(saved.read_text(encoding='utf-8-sig').splitlines())==2)
        page.locator('#customer-reset').click()
        page.wait_for_function("document.querySelectorAll('#customers-body [data-customer]').length === 40")
        page.screenshot(path=str(OUT/'03_客户查询.png'),full_page=True)
        with page.expect_response(lambda r:'/api/customers?' in r.url and 'page=2' in r.url):
            page.locator('#next-page').click()
        page.wait_for_function("document.getElementById('page-info').textContent.includes('第 2 /')")
        check('下一页可用', '第 2 /' in page.locator('#page-info').inner_text())
        page.locator('[data-nav="data"]').click()
        page.locator('#batches-body tr').first.wait_for()
        check('质量报告和下载显示',page.locator('#quality-downloads a').count()==3)
        check('首要排除原因按实际处理优先级展示',page.locator('#quality-body tr').nth(0).locator('td').first.inner_text()=='无效交易时间' and page.locator('#quality-body tr').nth(1).locator('td').first.inner_text()=='观察窗口外')
        page.locator('#toast').wait_for(state='hidden')
        page.screenshot(path=str(OUT/'05_数据管理.png'),full_page=True)
        with page.expect_response(lambda r:'/api/import' in r.url and r.status==200):
            page.locator('#import-submit').click()
        page.wait_for_function("document.getElementById('job-status').textContent.includes('相同文件')")
        check('页面导入复用同文件批次','相同文件' in page.locator('#job-status').inner_text())
        page.locator('[data-nav="overview"]').click()
        page.locator('#sales-start').fill('2017-01-01')
        page.locator('#sales-end').fill('2017-02-01')
        with page.expect_response(lambda r:'/api/sales?' in r.url):
            page.locator('#sales-filter button[type="submit"]').click()
        page.wait_for_function("document.getElementById('metric-lines').textContent !== '356,346'")
        check('销售日期筛选更新实际卡片',page.locator('#metric-lines').inner_text() not in ('—','356,346'))
        page.locator('#sales-reset').click()
        page.wait_for_function("document.getElementById('metric-lines').textContent==='356,346'")
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_timeout(350)
        check('移动宽度页面无横向溢出',page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
        page.screenshot(path=str(OUT/'06_窄屏布局.png'),full_page=True)
        check('浏览器无JavaScript异常',not errors)
        browser.close()
    (ROOT/'docs/浏览器验证结果.json').write_text(json.dumps({'checks':checks,'javascript_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
