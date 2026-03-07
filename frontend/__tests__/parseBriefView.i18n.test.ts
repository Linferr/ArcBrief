import { describe, expect, it } from 'vitest';

import { parseBriefView } from '../app/components/NewsFeedPanel';

describe('parseBriefView i18n parsing', () => {
  it('parses Chinese brief sections into structured entries and sources', () => {
    const content = `## 📌 今日核心

### 每日总结
**模型供应链变化加速**
主流模型厂商开始调整推理和分发策略。
**关键要点**
- OpenAI 调整产品打包方式
- Anthropic 强化企业接口
*情绪: neutral | 可信度: high*
(相关文章: 3)

## 来源索引

- OpenAI update [OpenAI Blog] (2026-03-06) [published_at]`;

    const parsed = parseBriefView(content);

    expect(parsed.entries).toHaveLength(1);
    expect(parsed.entries[0].headline).toBe('模型供应链变化加速');
    expect(parsed.entries[0].takeaways).toEqual([
      'OpenAI 调整产品打包方式',
      'Anthropic 强化企业接口',
    ]);
    expect(parsed.entries[0].reliability).toBe('high');
    expect(parsed.entries[0].relatedArticles).toBe(3);
    expect(parsed.sources).toHaveLength(1);
  });

  it('parses Japanese source header and related article labels', () => {
    const content = `## 📂 テーマ別動向

### Daily Executive Summary
**MCP adoption expands**
Ecosystem support is widening.
**重要ポイント**
- LangChain integration matured
*センチメント: neutral | 信頼性: med*
(関連記事: 2)

## ソース

- MCP update [GitHub] (2026-03-06) [published_at]`;

    const parsed = parseBriefView(content);

    expect(parsed.entries).toHaveLength(1);
    expect(parsed.entries[0].headline).toBe('MCP adoption expands');
    expect(parsed.entries[0].takeaways).toEqual(['LangChain integration matured']);
    expect(parsed.entries[0].relatedArticles).toBe(2);
    expect(parsed.sources).toHaveLength(1);
  });
});
