import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Wordmark } from '@/components/wordmark';

export default function NotFound() {
  return (
    <main id="main" className="flex min-h-dvh flex-col items-center justify-center gap-6 px-5">
      <Wordmark size="large" />
      <p className="text-sm text-muted-foreground">That page does not exist.</p>
      <Button variant="outline" asChild>
        <Link href="/">Back to search</Link>
      </Button>
    </main>
  );
}
