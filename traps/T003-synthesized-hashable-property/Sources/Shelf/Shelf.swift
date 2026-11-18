import Core

public func capacity(_ boxes: [Box]) -> Int { boxes.reduce(0) { $0 + $1.size } }
