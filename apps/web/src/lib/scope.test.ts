import { describe, expect, it } from "vitest";
import { padBounds, parseBounds, parseList } from "./scope";

describe("parseBounds", () => {
  it("reads south,west,north,east", () => {
    expect(parseBounds("-21.2,27.6,-19.2,29.6")).toEqual([
      [-21.2, 27.6],
      [-19.2, 29.6],
    ]);
  });

  it("ignores spaces", () => {
    expect(parseBounds(" -21.2 , 27.6 , -19.2 , 29.6 ")).not.toBeNull();
  });

  it.each([undefined, "", "1,2,3", "a,b,c,d", "-19,27,-21,29", "-21,29,-19,27", "-95,27,-19,29"])("rejects %s", (raw) => {
    expect(parseBounds(raw)).toBeNull();
  });
});

describe("parseList", () => {
  it("splits, trims and drops blanks", () => {
    expect(parseList("Bulawayo, Matabeleland North ,,")).toEqual(["Bulawayo", "Matabeleland North"]);
  });

  it("means no restriction when empty", () => {
    expect(parseList(undefined)).toBeNull();
    expect(parseList(" , ")).toBeNull();
  });
});

describe("padBounds", () => {
  it("widens each side", () => {
    expect(
      padBounds(
        [
          [-21, 27],
          [-19, 29],
        ],
        0.5,
      ),
    ).toEqual([
      [-21.5, 26.5],
      [-18.5, 29.5],
    ]);
  });
});
