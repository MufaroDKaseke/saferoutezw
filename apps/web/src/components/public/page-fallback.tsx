import { LoadingText } from "@/components/public/loading-text";
import { Container } from "@/components/public/site-chrome";

/**
 * Shown while a public page reads the visitor's language. Every public page wraps its content in a Suspense
 * boundary with this fallback: the layout's own boundary does not count when you move between pages,
 * because the layout stays mounted (Cache Components' instant-navigation rule).
 */
export function PageFallback() {
  return (
    <Container className="py-10">
      <LoadingText />
    </Container>
  );
}
