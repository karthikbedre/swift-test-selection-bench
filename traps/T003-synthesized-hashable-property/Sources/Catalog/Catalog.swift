import Core

public enum Catalog {
    public static func uniqueCount(_ tags: [Tag]) -> Int { Set(tags).count }
}
