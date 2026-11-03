import ReactMarkdown, { type Components, type UrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

const allowedElements = [
  "p",
  "br",
  "hr",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "strong",
  "em",
  "del",
  "blockquote",
  "ul",
  "ol",
  "li",
  "pre",
  "code",
  "a",
  "img",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
  "input",
  "section",
  "sup",
];

const safeUrl: UrlTransform = (url, key) => {
  // Images must never trigger requests, including same-origin and tracking URLs.
  if (key !== "href" || /[\u0000-\u0020\u007f\\]/u.test(url)) return undefined;
  if (url.startsWith("#")) return url;
  if (!/^https?:\/\//i.test(url)) return undefined;

  try {
    const parsed = new URL(url);

    if (parsed.username || parsed.password) return undefined;

    return parsed.href;
  } catch {
    return undefined;
  }
};

const components: Components = {
  a: ({ href, children }) =>
    href ? (
      <a
        href={href}
        target={href.startsWith("#") ? undefined : "_blank"}
        rel="noopener noreferrer"
        referrerPolicy="no-referrer"
      >
        {children}
      </a>
    ) : (
      <span>{children}</span>
    ),
  img: ({ alt }) => <span>{alt || "Image omitted"}</span>,
};

export function SafeMarkdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      skipHtml
      allowedElements={allowedElements}
      remarkPlugins={[remarkGfm]}
      urlTransform={safeUrl}
      components={components}
    >
      {children}
    </ReactMarkdown>
  );
}
