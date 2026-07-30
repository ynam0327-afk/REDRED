const SHORT_URL_PATTERNS = ["vo.la", "bit.ly", "url.kr", "han.gl", "t.ly"];
const DANGER_KEYWORDS = ["긴급", "대피", "지금 즉시", "클릭", "인증"];
const URL_REGEX = /(https?:\/\/[^\s]+)/g;

export interface HeuristicScores {
  urlRiskScore: number;
  textAuthenticityScore: number;
  detectedUrls: string[];
}

// TODO: 팀원 URL/텍스트 모델이 API로 노출되면 이 함수를 그 호출로 교체
export function computeHeuristicScores(text: string): HeuristicScores {
  const detectedUrls = text.match(URL_REGEX) ?? [];
  const hasShortUrl = SHORT_URL_PATTERNS.some((p) => text.includes(p));
  const hasDangerKeyword = DANGER_KEYWORDS.some((k) => text.includes(k));

  let urlRiskScore = 0.1;
  if (detectedUrls.length > 0) urlRiskScore = 0.4;
  if (hasShortUrl) urlRiskScore = 0.9;

  let textAuthenticityScore = 0.7;
  if (hasDangerKeyword) textAuthenticityScore = 0.4;
  if (hasShortUrl && hasDangerKeyword) textAuthenticityScore = 0.15;

  return { urlRiskScore, textAuthenticityScore, detectedUrls };
}