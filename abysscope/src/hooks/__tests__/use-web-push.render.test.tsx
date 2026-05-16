// @vitest-environment happy-dom
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";

// next/navigation's useRouter pulls in a lot of app router context.
// The hook only calls router.push for notification-click side
// effects — stub it out so tests don't have to mount a router.
// vi.hoisted lets us share the spy with the hoisted mock factory.
const { routerPush } = vi.hoisted(() => ({ routerPush: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
}));

// Imported after the mock so the hook picks up our stub.
import { useWebPush } from "../use-web-push";

type NotificationPermission = "default" | "granted" | "denied";

interface PushFixtures {
  permission?: NotificationPermission;
  hasSubscription?: boolean;
  withCaches?: boolean;
}

function installPushAPIs(fixtures: PushFixtures = {}) {
  const subscription = {
    endpoint: "https://example.test/push/abc",
    toJSON: () => ({ endpoint: "https://example.test/push/abc" }),
    unsubscribe: vi.fn().mockResolvedValue(true),
  };
  const pushManager = {
    getSubscription: vi
      .fn()
      .mockResolvedValue(fixtures.hasSubscription ? subscription : null),
    subscribe: vi.fn().mockResolvedValue(subscription),
  };
  const registration = {
    pushManager,
    active: { postMessage: vi.fn() },
  };
  const serviceWorker = {
    register: vi.fn().mockResolvedValue(registration),
    ready: Promise.resolve(registration),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };

  Object.defineProperty(navigator, "serviceWorker", {
    value: serviceWorker,
    configurable: true,
  });

  class NotificationStub {
    static permission: NotificationPermission =
      fixtures.permission ?? "default";
    static requestPermission = vi
      .fn()
      .mockImplementation(() => Promise.resolve(NotificationStub.permission));
  }
  // The hook reads the bare `Notification` / `PushManager` globals; in
  // happy-dom those resolve via globalThis, so stubbing `window.X`
  // alone is not enough.
  vi.stubGlobal("Notification", NotificationStub);
  vi.stubGlobal("PushManager", function PushManager() {});

  if (fixtures.withCaches !== false) {
    const cacheStore = new Map<string, Response>();
    const cache = {
      match: vi.fn().mockImplementation(async (key: string) =>
        cacheStore.get(key) ?? null,
      ),
      delete: vi.fn().mockImplementation(async (key: string) =>
        cacheStore.delete(key),
      ),
      put: vi.fn().mockImplementation(async (key: string, value: Response) => {
        cacheStore.set(key, value);
      }),
    };
    Object.defineProperty(window, "caches", {
      value: { open: vi.fn().mockResolvedValue(cache) },
      configurable: true,
    });
  }

  return { serviceWorker, pushManager, subscription, NotificationStub };
}

function uninstallPushAPIs() {
  delete (navigator as unknown as { serviceWorker?: unknown }).serviceWorker;
  delete (window as unknown as { Notification?: unknown }).Notification;
  delete (window as unknown as { PushManager?: unknown }).PushManager;
  delete (window as unknown as { caches?: unknown }).caches;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetchMock);
  localStorage.clear();
});

afterEach(() => {
  // React cleanup runs hook destructors that touch serviceWorker /
  // window APIs — tear those down BEFORE removing the mocks so we
  // don't crash inside removeEventListener.
  cleanup();
  uninstallPushAPIs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  routerPush.mockReset();
});

describe("useWebPush — status detection", () => {
  it('returns "unsupported" when the browser lacks PushManager', async () => {
    // No Notification / PushManager / serviceWorker installed.
    const { result } = renderHook(() =>
      useWebPush({ disableVisibilityTracking: true }),
    );
    await waitFor(() => expect(result.current.status).toBe("unsupported"));
  });

  it('reports "permission-denied" when Notification.permission is denied', async () => {
    installPushAPIs({ permission: "denied" });
    const { result } = renderHook(() =>
      useWebPush({ disableVisibilityTracking: true }),
    );
    await waitFor(() =>
      expect(result.current.status).toBe("permission-denied"),
    );
  });

  it('reports "permission-default" when permission hasn\'t been asked yet', async () => {
    installPushAPIs({ permission: "default" });
    const { result } = renderHook(() =>
      useWebPush({ disableVisibilityTracking: true }),
    );
    await waitFor(() =>
      expect(result.current.status).toBe("permission-default"),
    );
  });

  it('reports "permission-granted" when permission is granted but no subscription exists', async () => {
    installPushAPIs({ permission: "granted", hasSubscription: false });
    const { result } = renderHook(() =>
      useWebPush({ disableVisibilityTracking: true }),
    );
    await waitFor(() =>
      expect(result.current.status).toBe("permission-granted"),
    );
  });

  it('reports "subscribed" when permission is granted and a subscription exists', async () => {
    installPushAPIs({ permission: "granted", hasSubscription: true });
    const { result } = renderHook(() =>
      useWebPush({ disableVisibilityTracking: true }),
    );
    await waitFor(() => expect(result.current.status).toBe("subscribed"));
  });
});

describe("useWebPush — enable()", () => {
  it("short-circuits with an error when push is not supported", async () => {
    const { result } = renderHook(() =>
      useWebPush({ disableVisibilityTracking: true }),
    );
    await act(async () => {
      await result.current.enable();
    });
    expect(result.current.error).toMatch(/does not support web push/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sets permission-denied state when the user blocks the prompt", async () => {
    const apis = installPushAPIs({ permission: "default" });
    apis.NotificationStub.requestPermission.mockResolvedValueOnce("denied");
    const { result } = renderHook(() =>
      useWebPush({ disableVisibilityTracking: true }),
    );
    await act(async () => {
      await result.current.enable();
    });
    expect(result.current.status).toBe("permission-denied");
    expect(result.current.error).toMatch(/blocked/i);
  });

  it("fetches the VAPID key, subscribes, POSTs to /api/push/subscribe, and flips to subscribed", async () => {
    const apis = installPushAPIs({
      permission: "default",
      hasSubscription: false,
    });
    apis.NotificationStub.requestPermission.mockResolvedValueOnce("granted");
    // A real VAPID public key is a URL-safe base64 string ~87 chars.
    // The atob() call inside urlBase64ToUint8Array rejects non-base64
    // characters with "Invalid character", so the fixture must decode
    // cleanly even if the bytes are meaningless.
    const fakeVapidKey =
      "BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    fetchMock.mockImplementation(async (url: string) => {
      if (url === "/api/push/vapid-key") {
        return {
          ok: true,
          json: async () => ({ publicKey: fakeVapidKey }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });

    const { result } = renderHook(() =>
      useWebPush({ disableVisibilityTracking: true }),
    );
    await act(async () => {
      await result.current.enable();
    });
    expect(result.current.status).toBe("subscribed");
    expect(apis.pushManager.subscribe).toHaveBeenCalled();
    const subscribePostCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/api/push/subscribe" &&
        (init as RequestInit | undefined)?.method === "POST",
    );
    expect(subscribePostCall).toBeDefined();
    const body = JSON.parse(
      (subscribePostCall![1] as RequestInit).body as string,
    );
    expect(body.endpoint).toBe("https://example.test/push/abc");
    expect(typeof body.device_id).toBe("string");
  });
});

describe("useWebPush — visibility tracking", () => {
  it("does NOT POST visibility when disableVisibilityTracking is set", async () => {
    installPushAPIs({ permission: "granted", hasSubscription: true });
    renderHook(() => useWebPush({ disableVisibilityTracking: true }));
    // give the hook a microtask tick
    await Promise.resolve();
    const visibilityCalls = fetchMock.mock.calls.filter(
      ([url]) => url === "/api/push/visibility",
    );
    expect(visibilityCalls).toHaveLength(0);
  });

  it("pings /api/push/visibility on focus and blur", async () => {
    installPushAPIs({ permission: "granted", hasSubscription: true });
    renderHook(() => useWebPush());

    // Initial mount ping fires once.
    await waitFor(() => {
      const calls = fetchMock.mock.calls.filter(
        ([url]) => url === "/api/push/visibility",
      );
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });

    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    act(() => {
      window.dispatchEvent(new Event("blur"));
    });

    const calls = fetchMock.mock.calls.filter(
      ([url]) => url === "/api/push/visibility",
    );
    expect(calls.length).toBeGreaterThanOrEqual(3);

    const bodies = calls.map(
      ([, init]) => JSON.parse((init as RequestInit).body as string) as {
        visible: boolean;
      },
    );
    expect(bodies.some((b) => b.visible === true)).toBe(true);
    expect(bodies.some((b) => b.visible === false)).toBe(true);
  });
});
