// Module-level flag: the QAM opens the setup page with "force" preselected.
let force = false;
export const setupIntent = {
  get force() {
    return force;
  },
  set force(v: boolean) {
    force = v;
  },
};
