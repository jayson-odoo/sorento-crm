'use client';

/**
 * The fixed backdrop behind the credential pages. Purely decorative, so it is `aria-hidden` and
 * takes no pointer events; the card in front of it owns every interaction.
 *
 * With no `imageUrl` the designed wash in `css/components/auth-backdrop.css` is the whole design.
 * With one, the photo layers over the wash under a scrim, and the wash still shows through the
 * photo's transparent edges and while it is loading, so there is never a white flash.
 */
export function AuthBackdrop({ imageUrl }: { imageUrl?: string | null }) {
  return (
    <div className="auth-backdrop" aria-hidden="true">
      {imageUrl ? (
        <>
          <div
            className="auth-backdrop-photo"
            style={{ backgroundImage: `url(${JSON.stringify(imageUrl)})` }}
          />
          <div className="auth-backdrop-scrim" />
        </>
      ) : null}
    </div>
  );
}
