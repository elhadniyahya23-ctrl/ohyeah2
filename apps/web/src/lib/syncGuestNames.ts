import { fetchNamesCount, saveNames } from "@/lib/namesApi";
import { getGlobalNames } from "@/lib/globalStore";

export interface GuestSyncResult {
  uploaded: number;
  skippedBecauseServerHasNames: boolean;
}

/** Upload guest localStorage names to the server when the account has none yet. */
export async function syncGuestNamesToServer(): Promise<GuestSyncResult> {
  const local = getGlobalNames();
  if (!local.length) {
    return { uploaded: 0, skippedBecauseServerHasNames: false };
  }

  try {
    const { count } = await fetchNamesCount();
    if (count > 0) {
      return { uploaded: 0, skippedBecauseServerHasNames: true };
    }
    const result = await saveNames(local.join("\n"), false);
    return { uploaded: result.count, skippedBecauseServerHasNames: false };
  } catch {
    return { uploaded: 0, skippedBecauseServerHasNames: false };
  }
}
