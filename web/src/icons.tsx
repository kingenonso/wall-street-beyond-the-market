import type { ProfileIcon } from "./api";

/** The two standard profile pictures. A player picks one; uploading their own comes in a later stage. */
export function ProfilePicture({ icon, name, size = 44 }: { icon: ProfileIcon | null; name: string; size?: number }) {
  const inner = Math.round(size * 0.6);
  return (
    <span className="avatar" style={{ width: size, height: size }} aria-hidden="true">
      {icon === null ? (
        <span style={{ fontSize: Math.round(size * 0.4) }}>{name.charAt(0).toUpperCase()}</span>
      ) : (
        <svg viewBox="0 0 40 40" width={inner} height={inner} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          {icon === "male" ? (
            <>
              <circle cx="20" cy="14" r="7" />
              <path d="M6 36c0-8 6-12 14-12s14 4 14 12" />
            </>
          ) : (
            <>
              <path d="M11 24V14a9 9 0 0 1 18 0v10" />
              <circle cx="20" cy="15" r="6" />
              <path d="M6 36c0-7 6-11 14-11s14 4 14 11" />
            </>
          )}
        </svg>
      )}
    </span>
  );
}
