import { describe, expect, it } from "vitest"

import { whyLocked } from "./people-page"
import type { ManagedUser } from "@/lib/api"

const user = (over: Partial<ManagedUser> = {}): ManagedUser => ({
  id: 2,
  email: "someone@stocklens.local",
  display_name: null,
  role: "user",
  is_active: true,
  created_at: null,
  last_login_at: null,
  saved_screens: 0,
  watchlists: 0,
  ...over,
})

const superAdmin = { id: 1, role: "super_admin" }
const admin = { id: 1, role: "admin" }

/**
 * These mirror rules the server enforces. The page disables the control and says
 * why, rather than offering it and letting the request fail - but the server is
 * the boundary, and these tests exist so the two do not drift apart.
 */
describe("whyLocked", () => {
  it("lets a super admin change an ordinary account", () => {
    expect(whyLocked(user(), superAdmin, 2)).toBeNull()
  })

  it("stops you changing your own role", () => {
    // Demoting yourself mid-task is the ordinary way to lose the console.
    expect(whyLocked(user({ id: 1 }), superAdmin, 2)).toMatch(/your own/i)
  })

  it("stops an admin acting on a super admin", () => {
    // Otherwise an admin could promote themselves and the roles collapse.
    expect(whyLocked(user({ role: "super_admin" }), admin, 2)).toMatch(/super administrator/i)
  })

  it("protects the last active super admin", () => {
    expect(whyLocked(user({ role: "super_admin" }), superAdmin, 1)).toMatch(/last active/i)
  })

  it("allows demoting a super admin while another remains", () => {
    expect(whyLocked(user({ role: "super_admin" }), superAdmin, 2)).toBeNull()
  })

  it("does not protect an already suspended super admin", () => {
    // It is not holding the door open, so the count that matters excludes it.
    expect(whyLocked(user({ role: "super_admin", is_active: false }), superAdmin, 1)).toBeNull()
  })

  it("puts your own account ahead of every other reason", () => {
    // A lone super admin looking at themselves should be told the plain thing.
    expect(whyLocked(user({ id: 1, role: "super_admin" }), superAdmin, 1)).toMatch(/your own/i)
  })
})
