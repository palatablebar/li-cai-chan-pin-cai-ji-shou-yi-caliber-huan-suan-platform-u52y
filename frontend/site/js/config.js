/**
 * 品牌、导航、角色权限与枚举文案（前端唯一定义处）。
 * 后端对应：backend/src/constants/{roles,enums}.py；README「共享枚举出现位置」列出全部出现点。
 */
export const BRAND = {
  short: 'yieldbook',
  title: '理财产品采集与收益口径换算台',
  org: '江城银行 · 财富管理部产品组',
  edition: 'CATALOGUE · 2026',
  catalogueNo: '第 03 号 · 代销产品目录',
  subtitle: '68 只代销产品 · 8 家合作机构 · 四种收益口径归一再比较',
  loginLead:
    '七日年化、万份收益、净值区间、业绩基准四种口径，先在系统里换算成可比年化，再谈同类排名。',
  loginPoints: [
    ['01', '产品入库', '官网与 APP 的要素统一登记，起购金额与风险等级不再漏填'],
    ['02', '口径归一', '万份收益 / 净值区间 / 七日年化 / 基准中值，缺失标 unknown 不猜'],
    ['03', '同类排名', '类型 + 期限档分组，样本 <5 不排名，波动为 0 用同类中位数'],
  ],
  coverFoot: ['财富管理部 · 产品组 4 人', '内部资料 · 不得外传'],
};

export const NAV = [
  { to: '#/overview', no: '01', label: '总览', permission: 'overview:read' },
  { to: '#/products', no: '02', label: '产品库', permission: 'product:read' },
  { to: '#/compare', no: '03', label: '对比榜', permission: 'yield:read' },
  { to: '#/watchlist', no: '04', label: '关注与到期', permission: 'watch:read' },
  { to: '#/runs', no: '05', label: '换算与导入', permission: 'yield:read' },
  { to: '#/audit', no: '06', label: '审计日志', permission: 'audit:read' },
];

export const ROLE_LABELS = {
  admin: '产品经理',
  analyst: '口径专员',
  viewer: '客户经理',
};

export const PERMISSIONS = {
  admin: [
    'overview:read',
    'product:read',
    'product:write',
    'quote:read',
    'quote:import',
    'yield:read',
    'yield:run',
    'yield:review',
    'watch:read',
    'watch:write',
    'export:read',
    'audit:read',
  ],
  analyst: [
    'overview:read',
    'product:read',
    'quote:read',
    'quote:import',
    'yield:read',
    'yield:run',
    'yield:review',
    'watch:read',
    'watch:write',
  ],
  viewer: ['overview:read', 'product:read', 'quote:read', 'yield:read', 'watch:read'],
};

/** 共享枚举（与 backend/src/constants/enums.py 一一对应） */
export const ENUMS = {
  productType: {
    cash: '现金管理类',
    fixed: '固定收益类',
    mixed: '混合类',
    equity: '权益类',
  },
  riskLevel: {
    R1: 'R1 谨慎型',
    R2: 'R2 稳健型',
    R3: 'R3 平衡型',
    R4: 'R4 成长型',
    R5: 'R5 进取型',
  },
  termBucket: {
    le30: '≤30 天',
    d31_180: '31-180 天',
    d181_365: '181-365 天',
    gt365: '>365 天',
    unknown: '期限未知',
  },
  method: {
    direct: '七日年化直取',
    wanfen: '万份收益折算',
    nav: '净值区间年化',
    bench: '业绩基准中值',
    unknown: '口径缺失',
  },
  confidence: {
    high: '高',
    medium: '中',
    low: '低',
    none: '无',
  },
  review: {
    pending: '待复核',
    confirmed: '已确认',
    dismissed: '已驳回',
  },
  runStatus: {
    running: '执行中',
    success: '成功',
    partial: '部分成功',
    failed: '失败',
  },
  trigger: {
    manual: '手动',
    schedule: '定时',
    seed: '初始化',
  },
  watchKind: {
    expire: '到期提醒',
    rank: '排名变动',
  },
  watchStatus: {
    pending: '待跟进',
    notified: '已通知',
    done: '已处理',
  },
  quoteSource: {
    seed: '初始化导入',
    import: '机构批量导入',
    manual: '手工补录',
  },
};

export function can(role, permission) {
  return (PERMISSIONS[role] || []).includes(permission);
}

export function methodTone(method) {
  return (
    { direct: 'ok', wanfen: 'info', nav: 'copper', bench: 'medium', unknown: 'danger' }[method] || 'info'
  );
}

export function reviewTone(status) {
  return { pending: 'pending warn', confirmed: 'ok', dismissed: 'danger' }[status] || 'info';
}

export function runTone(status) {
  return { success: 'ok', partial: 'medium', failed: 'danger', running: 'info' }[status] || 'info';
}

export function riskTone(level) {
  return { R1: 'ok', R2: 'info', R3: 'copper', R4: 'medium', R5: 'danger' }[level] || 'info';
}

export function watchTone(status) {
  return { pending: 'pending warn', notified: 'info', done: 'ok' }[status] || 'info';
}
