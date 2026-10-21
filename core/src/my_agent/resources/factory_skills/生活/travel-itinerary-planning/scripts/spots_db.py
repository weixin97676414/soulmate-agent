#!/usr/bin/env python3
# -*- coding: utf-8 -*-











import argparse, json





CITIES = {
 "重庆": {
  "解放碑": [106.5776, 29.5573, "免费", False, "🗼", "重庆市中心地标", "Jiefangbei Chongqing"],
  "洪崖洞": [106.5796, 29.5621, "免费", False, "🌉", "现实版千与千寻夜景", "Hongya Cave"],
  "千厮门大桥": [106.5843, 29.5650, "免费", False, "🌉", "两江夜景机位", "Qiansimen Bridge"],
  "长江索道": [106.5836, 29.5581, "约¥30", True, "🚠", "跨江空中走廊", "Chongqing Yangtze River Cableway"],
  "李子坝": [106.5358, 29.5486, "免费", False, "🚝", "2号线轻轨穿楼", "Liziba Station"],
  "皇冠大扶梯": [106.5424, 29.5548, "约¥2", True, "🛗", "世界最长扶梯", "Crown escalator Chongqing"],
  "三峡博物馆": [106.5472, 29.5620, "免费·需预约", False, "🏛", "巴渝人文", "Chongqing Three Gorges Museum"],
  "人民大礼堂": [106.5495, 29.5609, "免费", False, "🏛", "重庆地标建筑", "Chongqing People's Auditorium"],
  "十八梯": [106.5714, 29.5532, "免费", False, "🏘", "老城焕新", "Shibati Chongqing"],
  "山城步道": [106.5652, 29.5498, "免费", False, "🥾", "老重庆梯坎·观长江", "Mountain city trail Chongqing"],
  "湖广会馆": [106.5845, 29.5518, "约¥30", True, "🏯", "清代移民会馆", "Huguang Guild Hall"],
  "龙门浩老街": [106.5882, 29.5506, "免费", False, "🏘", "南滨江景老街", "Longmenhao"],
  "南山一棵树": [106.5963, 29.5373, "约¥30", True, "🌃", "俯瞰渝中半岛夜景", "Chongqing night view"],
  "磁器口": [106.4612, 29.5750, "免费", False, "🏘", "千年古镇·美食", "Ciqikou"],
  "渣滓洞": [106.4240, 29.5830, "免费·需预约", False, "🏛", "红色人文遗址", "Zhaizidong Prison"],
  "观音桥": [106.5320, 29.5830, "免费", False, "🛍", "商圈·九街夜生活", "Guanyinqiao"],
  "朝天门/两江游": [106.5900, 29.5670, "约¥120", True, "⛴", "两江交汇·夜游", "Chongqing Chaotianmen"],
 },
 "成都": {
  "宽窄巷子": [104.0588, 30.6695, "免费", False, "🏘", "清代川西民居老街", "Kuanzhai Alley"],
  "锦里": [104.0494, 30.6432, "免费", False, "🏘", "三国主题老街", "Jinli Chengdu"],
  "武侯祠": [104.0473, 30.6458, "约¥50", True, "🏛", "三国文化博物馆", "Wuhou Shrine"],
  "大熊猫基地": [104.1390, 30.7360, "约¥55", True, "🐼", "看滚滚·早去", "Chengdu Research Base Giant Panda"],
  "春熙路": [104.0813, 30.6565, "免费", False, "🛍", "核心商圈", "Chunxi Road"],
  "太古里": [104.0830, 30.6530, "免费", False, "🛍", "潮流街区", "Taikoo Li Chengdu"],
  "杜甫草堂": [104.0279, 30.6610, "约¥50", True, "🏛", "诗圣故居", "Du Fu Thatched Cottage"],
  "青城山": [103.5960, 30.9000, "约¥80", True, "⛰", "道教名山·前山", "Mount Qingcheng"],
  "都江堰": [103.6195, 31.0040, "约¥80", True, "🌊", "千年水利工程", "Dujiangyan"],
  "九眼桥": [104.0880, 30.6310, "免费", False, "🌉", "酒吧街·夜景", "Jiuyanqiao"],
  "人民公园": [104.0610, 30.6570, "免费", False, "🌳", "喝盖碗茶·鹤鸣茶社", "People's Park Chengdu"],
  "望江楼": [104.0970, 30.6200, "免费", False, "🏯", "薛涛纪念园林", "Wangjiang Tower Chengdu"],
 },
 "西安": {
  "兵马俑": [109.2767, 34.3853, "约¥120", True, "🗿", "世界第八大奇迹", "Terracotta Army"],
  "大雁塔": [108.9640, 34.2186, "约¥50", True, "🗼", "玄奘译经处", "Giant Wild Goose Pagoda"],
  "大唐不夜城": [108.9630, 34.2190, "免费", False, "🌃", "盛唐夜景步行街", "Datang Everbright City"],
  "回民街": [108.9400, 34.2640, "免费", False, "🍜", "小吃街·牛羊肉泡馍", "Muslim Quarter Xi'an"],
  "钟楼": [108.9470, 34.2610, "约¥30", True, "🏯", "西安中心地标", "Xi'an Bell Tower"],
  "鼓楼": [108.9430, 34.2610, "约¥30", True, "🏯", "晨钟暮鼓", "Xi'an Drum Tower"],
  "西安城墙": [108.9400, 34.2520, "约¥54", True, "🏰", "可骑行城墙", "Xi'an City Wall"],
  "陕西历史博物馆": [108.9520, 34.2250, "免费·需预约", False, "🏛", "古都文明宝库", "Shaanxi History Museum"],
  "华清宫": [109.2130, 34.3650, "约¥120", True, "🏯", "唐宫汤池·长恨歌", "Huaqing Pool"],
  "永兴坊": [108.9670, 34.2760, "免费", False, "🍜", "摔碗酒·美食街", "Yongxingfang"],
 },
 "杭州": {
  "西湖": [120.1500, 30.2420, "免费", False, "🌊", "世界文化遗产", "West Lake Hangzhou"],
  "断桥": [120.1510, 30.2570, "免费", False, "🌉", "白蛇传说·西湖十景", "Broken Bridge Hangzhou"],
  "灵隐寺": [120.1000, 30.2400, "约¥45", True, "🏯", "千年古刹·飞来峰", "Lingyin Temple"],
  "雷峰塔": [120.1480, 30.2310, "约¥40", True, "🗼", "白娘子传说·俯瞰西湖", "Leifeng Pagoda"],
  "河坊街": [120.1730, 30.2420, "免费", False, "🍜", "杭城小吃街", "Hefang Street"],
  "苏堤": [120.1370, 30.2460, "免费", False, "🌳", "苏东坡筑堤·漫步", "Su Causeway"],
  "三潭印月": [120.1410, 30.2430, "免费", False, "⛴", "一元纸币背面取景", "Three Pools Mirroring Moon"],
  "西溪湿地": [120.0640, 30.2680, "约¥80", True, "🌿", "城市湿地·摇橹船", "Xixi Wetland"],
  "京杭大运河": [120.1600, 30.3100, "免费", False, "🌊", "千年漕运·拱宸桥", "Grand Canal Hangzhou"],
  "龙井村": [120.1080, 30.2220, "免费", False, "🍵", "龙井茶产地·品茶", "Longjing tea village"],
 },
 "北京": {
  "故宫": [116.3970, 39.9180, "约¥60(旺季)", True, "🏯", "明清皇宫·需预约", "Forbidden City"],
  "天安门": [116.3910, 39.9080, "免费", False, "🏛", "国门地标", "Tiananmen"],
  "八达岭长城": [116.0240, 40.3600, "约¥40", True, "⛰", "最经典长城段", "Badaling Great Wall"],
  "颐和园": [116.2730, 39.9990, "约¥30", True, "🏞", "皇家园林·昆明湖", "Summer Palace"],
  "天坛": [116.4070, 39.8820, "约¥15", True, "🏛", "祈年殿·明清祭天", "Temple of Heaven"],
  "南锣鼓巷": [116.4030, 39.9370, "免费", False, "🏘", "胡同文化街", "Nanluoguxiang"],
  "什刹海": [116.3890, 39.9400, "免费", False, "🌊", "后海·胡同·夜景", "Shichahai"],
  "王府井": [116.4110, 39.9100, "免费", False, "🛍", "百年商业街", "Wangfujing"],
  "鸟巢/水立方": [116.3900, 39.9930, "约¥50", True, "🏟", "奥运场馆", "Bird's Nest Beijing"],
  "三里屯": [116.4530, 39.9360, "免费", False, "🛍", "潮流夜生活", "Sanlitun"],
 },
 "上海": {
  "外滩": [121.4900, 31.2400, "免费", False, "🌃", "万国建筑·夜景", "The Bund Shanghai"],
  "东方明珠": [121.4990, 31.2390, "约¥220", True, "🗼", "陆家嘴地标·观景", "Oriental Pearl Tower"],
  "豫园": [121.4920, 31.2270, "约¥40", True, "🏯", "明代江南园林", "Yuyuan Garden"],
  "城隍庙": [121.4940, 31.2270, "免费", False, "🏛", "老上海小吃", "City God Temple Shanghai"],
  "南京路": [121.4780, 31.2360, "免费", False, "🛍", "中华商业第一街", "Nanjing Road"],
  "田子坊": [121.4700, 31.2110, "免费", False, "🏘", "石库门创意街区", "Tianzifang"],
  "新天地": [121.4770, 31.2210, "免费", False, "🏘", "石库门时尚地标", "Xintiandi"],
  "上海迪士尼": [121.6570, 31.1440, "约¥500", True, "🎢", "主题乐园", "Shanghai Disneyland"],
  "陆家嘴": [121.5030, 31.2400, "免费", False, "🏙", "金融中心·三件套", "Lujiazui"],
  "武康路": [121.4380, 31.2050, "免费", False, "🌳", "梧桐街道·老洋房", "Wukang Road"],
 },
 "广州": {
  "广州塔": [113.3240, 23.1060, "约¥150", True, "🗼", "小蛮腰·摩天轮", "Canton Tower"],
  "沙面": [113.2400, 23.1090, "免费", False, "🏘", "欧陆风情老街区", "Shamian Island"],
  "陈家祠": [113.2450, 23.1310, "约¥10", True, "🏛", "岭南建筑瑰宝", "Chen Clan Ancestral Hall"],
  "北京路": [113.2680, 23.1270, "免费", False, "🛍", "千年古道商业街", "Beijing Road Guangzhou"],
  "珠江夜游": [113.2790, 23.1160, "约¥80", True, "⛴", "一江两岸夜景", "Pearl River night cruise"],
  "白云山": [113.3030, 23.1800, "约¥5", True, "⛰", "羊城第一秀", "Baiyun Mountain"],
  "越秀公园": [113.2620, 23.1390, "免费", False, "🌳", "五羊石像", "Yuexiu Park"],
  "永庆坊": [113.2410, 23.1190, "免费", False, "🏘", "西关骑楼老街", "Yongqingfang"],
  "长隆": [113.3210, 23.0120, "约¥250", True, "🎢", "野生动物园+乐园", "Chimelong"],
 },
 "深圳": {
  "世界之窗": [113.9720, 22.5350, "约¥220", True, "🌍", "世界微缩景观", "Window of the World Shenzhen"],
  "欢乐谷": [113.9750, 22.5400, "约¥230", True, "🎢", "主题乐园", "Happy Valley Shenzhen"],
  "东部华侨城": [114.2680, 22.5940, "约¥200", True, "🏞", "山海度假区", "OCT East"],
  "大梅沙": [114.3120, 22.5990, "免费", False, "🏖", "海滨沙滩", "Dameisha Beach"],
  "莲花山公园": [114.0590, 22.5550, "免费", False, "🌳", "城市绿肺·观景", "Lianhuashan Park Shenzhen"],
  "深圳湾": [113.9500, 22.5110, "免费", False, "🌊", "滨海长廊·骑行", "Shenzhen Bay"],
  "市民中心": [114.0550, 22.5430, "免费", False, "🏛", "城市中轴线", "Shenzhen Civic Center"],
  "海上世界": [113.9160, 22.4870, "免费", False, "⛴", "明华轮·餐饮街区", "Sea World Shenzhen"],
  "华强北": [114.0850, 22.5470, "免费", False, "🛍", "电子数码商圈", "Huaqiangbei"],
 },
 "武汉": {
  "黄鹤楼": [114.3070, 30.5470, "约¥70", True, "🗼", "江南三大名楼", "Yellow Crane Tower"],
  "东湖": [114.3800, 30.5680, "免费", False, "🌊", "城中湖·绿道骑行", "East Lake Wuhan"],
  "户部巷": [114.3080, 30.5510, "免费", False, "🍜", "汉味小吃街", "Hubu Alley"],
  "长江大桥": [114.2930, 30.5510, "免费", False, "🌉", "万里长江第一桥", "Wuhan Yangtze River Bridge"],
  "楚河汉街": [114.3460, 30.5520, "免费", False, "🛍", "现代水岸商业街", "Chuhe Hanjie"],
  "湖北省博物馆": [114.3690, 30.5650, "免费·需预约", False, "🏛", "曾侯乙编钟·越王勾践剑", "Hubei Provincial Museum"],
  "江汉路": [114.2900, 30.5880, "免费", False, "🛍", "百年商业步行街", "Jianghan Road Wuhan"],
  "武汉大学": [114.3610, 30.5340, "免费", False, "🏛", "樱花季·老建筑", "Wuhan University"],
  "晴川阁": [114.2830, 30.5580, "免费", False, "🏯", "隔江望黄鹤楼", "Qingchuan Pavilion"],
 },
 "南京": {
  "中山陵": [118.8500, 32.0620, "免费", False, "🏛", "孙中山陵寝·392级台阶", "Sun Yat-sen Mausoleum"],
  "明孝陵": [118.8380, 32.0600, "约¥70", True, "🏯", "明太祖陵·世界遗产", "Ming Xiaoling Mausoleum"],
  "夫子庙": [118.7910, 32.0200, "免费", False, "🏘", "孔庙+秦淮风光", "Confucius Temple Nanjing"],
  "秦淮河": [118.7940, 32.0200, "免费", False, "🌊", "桨声灯影·画舫游", "Qinhuai River"],
  "玄武湖": [118.7960, 32.0720, "免费", False, "🌊", "皇家园林湖泊", "Xuanwu Lake"],
  "新街口": [118.7830, 32.0430, "免费", False, "🛍", "中华第一商圈", "Xinjiekou Nanjing"],
  "总统府": [118.7970, 32.0480, "约¥35", True, "🏛", "民国历史建筑群", "Presidential Palace Nanjing"],
  "南京博物院": [118.8310, 32.0410, "免费·需预约", False, "🏛", "一院六馆·民国馆", "Nanjing Museum"],
  "老门东": [118.7940, 32.0100, "免费", False, "🏘", "明清民居街区·小吃", "Laomendong"],
 },
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cities', action='store_true')
    ap.add_argument('--city')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--names')
    a = ap.parse_args()
    if a.cities:
        print('\n'.join(sorted(CITIES)))
        return
    if not a.city or a.city not in CITIES:
        print('未知城市，可选：', ', '.join(sorted(CITIES)))
        return
    spots = CITIES[a.city]
    if a.list:
        for k in spots:
            v = spots[k]
            print(f'{k}\t{v[0]},{v[1]}\t{v[2]}\t{v[4]}\t{v[5]}')
        return
    names = [n.strip() for n in a.names.split(',')] if a.names else []
    out = {}
    for n in names:
        if n in spots:
            v = spots[n]
            out[n] = {"lon": v[0], "lat": v[1], "tag": v[2], "pay": v[3],
                      "icon": v[4], "desc": v[5], "query": v[6]}
    print(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
